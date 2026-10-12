"""The coding-agent gate: Claude Code hook events in, license decisions out.

Claude Code calls its hooks over HTTP; the agent cannot skip them:

* ``UserPromptSubmit`` opens a *turn*: the request and a snapshot of the
  working tree, so the end of the turn can be checked against both.
* ``PreToolUse`` fires before every call, even with permissions bypassed:
  forbidden actions and loop stops are denied there, everything else passes.
* ``PermissionRequest`` fires only when Claude Code would show a prompt, so
  edits and reads that are already allowed never reach us. The call is
  classified into an action class and answered from that class's license in
  this repo: ``allow`` (earned), ``deny`` (never allowed) or no decision, which
  lets Claude Code ask the person as usual.
* ``PostToolUse`` / ``PostToolUseFailure`` report what happened. A tool that
  ran after we left the decision to the person means the person approved it;
  that approval is remembered for its command family. A failed action that
  changes things is evidence against its class and takes its level away.
* ``Stop`` closes the turn: actions that changed the repo become verified
  evidence only if the turn's checks pass (:mod:`verify`).

Every decision is a span (neatlogs + local mirror), every level change is a
git commit in the license ledger.
"""

from __future__ import annotations

import sqlite3
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from sololicense.coding import agents, budget, entire, jev, loops, remediation
from sololicense.coding import digest
from sololicense.coding import policy as policy_mod
from sololicense.coding.actions import ACTION_CLASSES, Classification, classify_tool, describe, edited_path
from sololicense.coding.ladder import CodingLadder
from sololicense.db.repositories import agent as agent_repo
from sololicense.observability.tracer import Trace, Tracer
from sololicense.services.git_ledger import GitLedger, LedgerEntry

# Classes whose non-zero exit is information, not a mistake: a failing test
# run is the agent doing its job.
DIAGNOSTIC = {"read", "test-run", "lint-format", "build"}
GATE_ACTOR = "system:coding-gate"
# Denied attempts in one turn after which the agent is stopped, not just refused.
INTERRUPT_AFTER_DENIALS = 3
# Decisions whose action actually ran, so a flagged turn holds them to account.
FLAGGABLE_OUTCOMES = ("ran", "verified", "observed", "failed")
# Asked before they run at L0 even with permissions bypassed. Unrecognised
# commands are not: in bypass mode that would prompt for nearly everything.
ASK_FIRST = frozenset({"file-delete", "deploy", "db-migrate"})


def _who(repo: str, agent: str = "", principal: str = "main") -> dict:
    """Attributes every span of a coding trace carries."""
    return {"repo": repo, "principal": principal, **({"agent": agent} if agent else {})}


def _principal(event: dict | None) -> str:
    """Read the trusted principal set by the native-hook normaliser."""
    return str((event or {}).get("_principal") or (event or {}).get("principal") or "main")


def turn_reason(conn: sqlite3.Connection, turn_id: int) -> str | None:
    row = agent_repo.get_turn(conn, turn_id)
    return row["reason"] if row else None


def _git(cwd: str, *args: str, timeout: float = 10.0) -> str:
    try:
        result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True,
                                timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def repo_of(cwd: str) -> tuple[str, str]:
    """(display name, root path) of the repository a hook ran in."""
    root = _git(cwd, "rev-parse", "--show-toplevel") or cwd
    return Path(root).name or root, root


def snapshot(cwd: str) -> str | None:
    """A commit object of the current working tree (or HEAD if it is clean),
    taken without touching the index, stash list or files."""
    return _git(cwd, "stash", "create") or _git(cwd, "rev-parse", "HEAD") or None


@dataclass
class CodingGate:
    conn: sqlite3.Connection
    tracer: Tracer
    ledger: GitLedger
    ladder: CodingLadder = field(default_factory=CodingLadder)
    jev_client: jev.JevClient = field(default_factory=jev.JevClient.from_env)
    # Turn checks (tests + scope); installed by verify.py. Returns (ok, reason, details).
    verifier: Callable[["CodingGate", sqlite3.Row, list[sqlite3.Row]], tuple[bool, str, dict]] | None = None
    # Finds the Entire checkpoint a failed turn can be explained from / rewound to.
    checkpoint_lookup: Callable[[str, str], dict | None] = entire.last_checkpoint
    _traces: dict[int, Trace] = field(default_factory=dict)
    _agent: str = "claude-code"

    # --- hooks ------------------------------------------------------------

    def user_prompt(self, event: dict) -> dict:
        session, cwd = str(event.get("session_id", "")), str(event.get("cwd", "."))
        repo, root = repo_of(cwd)
        agent_repo.ensure_repo(self.conn, repo, root)
        agent = str(event.get("_agent") or "claude-code")
        principal = _principal(event)
        trace = self.tracer.start_trace("coding.turn", defaults=_who(repo, agent, principal), session_id=session or None,
                                        session=session[:12])
        turn_id = agent_repo.open_turn(
            self.conn, session_id=session, repo=repo, cwd=root,
            prompt=str(event.get("prompt", ""))[:8000], base_ref=snapshot(root), trace_id=trace.trace_id,
            agent=agent, principal=principal,
        )
        self._traces[turn_id] = trace
        self.conn.execute(
            "INSERT INTO agent_sessions (session_id, agent, repo, principal, digest) VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(session_id, principal) DO UPDATE SET agent=excluded.agent, repo=excluded.repo, "
            "principal=excluded.principal, digest=excluded.digest",
            (session, agent, repo, principal, digest.state(self.conn, session, repo=repo, principal=principal)),
        )
        if not event.get("_implicit"):  # a turn opened for an agent without a prompt hook is not a person
            loops.new_prompt(self.conn, session)
        trace.span("turn.start", turn=turn_id, prompt=str(event.get("prompt", ""))[:300])
        answer: dict = {}
        if agent in agents.TAKES_CONTEXT:
            queued = agent_repo.take_remediations(self.conn, session)
            if queued:
                text = "\n\n".join(r["text"] for r in queued)
                trace.span("remediation.delivered", turn=turn_id, count=len(queued), text=text[:300],
                           kinds=",".join(r["kind"] for r in queued))
                answer = {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": text}}
        self.conn.commit()
        return answer

    def subagent_start(self, event: dict) -> dict:
        """Open an implicit turn and give a subagent its bounded license."""
        session, cwd = str(event.get("session_id", "")), str(event.get("cwd", "."))
        repo, root = repo_of(cwd)
        principal = _principal(event)
        agent_type = str(event.get("subagent_type") or principal.removeprefix("subagent:") or "unknown")
        rules = policy_mod.effective(self.conn, repo, root)
        if agent_type.lower() in {t.lower() for t in rules.subagent_deny_types}:
            reason = f"Blocked: this repo's policy forbids spawning subagent type '{agent_type}'."
            return {"decision": "deny", "reason": reason}
        self.user_prompt({**event, "prompt": "", "_implicit": True, "_principal": principal})
        summary = self._subagent_summary(repo, root, principal, rules)
        return {"hookSpecificOutput": {"hookEventName": "SubagentStart", "additionalContext": summary}}

    def subagent_stop(self, event: dict) -> dict:
        """Run the normal turn verifier for a subagent's isolated work."""
        return self.stop(event)

    def _subagent_summary(self, repo: str, root: str, principal: str, rules: policy_mod.Policy) -> str:
        levels = []
        for key, spec in ACTION_CLASSES.items():
            if key == "unknown":
                continue
            license_row = agent_repo.effective_license(self.conn, repo, key, principal,
                                                       max_level=rules.subagent_max, create=False)
            level = min(int(license_row["level"]), rules.ceilings[key])
            levels.append(f"{key}=L{level}")
        return (f"Solo License: {principal} starts with a lower trust ceiling in {repo}. "
                f"Work within these levels: {', '.join(levels)}. "
                "Actions outside the ceiling ask a person; do not push or change protected policy.")

    def pre_tool(self, event: dict) -> dict:
        """Claude Code's PreToolUse fires before every call in every permission
        mode, bypass included, where PermissionRequest may never fire. Only what
        no mode may skip is answered here: a forbidden action or a loop stop is
        denied (and recorded by :meth:`permission`, once: a denied call never
        reaches PermissionRequest); a freeze, or a deletion, deploy or migration
        at L0, asks (recorded by the PermissionRequest that follows). Anything
        else gets no decision and nothing is written, so PermissionRequest and
        the earned levels decide."""
        session, cwd = str(event.get("session_id", "")), str(event.get("cwd", "."))
        tool, tool_input = str(event.get("tool_name", "")), event.get("tool_input") or {}
        repo, root = repo_of(cwd)
        principal = _principal(event)
        result = classify_tool(tool, tool_input)
        rules = policy_mod.effective(self.conn, repo, root)
        subagent_denial = policy_mod.denied_subagent(rules, tool, tool_input)
        repeats = loops.seen(self.conn, session, loops.fingerprint(tool, tool_input)).count + 1
        over_budget = result.action_class != "read" and budget.check(self.conn, session, repo, rules.budget).blocked
        if (result.hard_deny or subagent_denial or policy_mod.denied(rules, tool, tool_input, root) or over_budget
                or loops.halted(self.conn, session) or repeats >= loops.STOP_AT):
            answer = self.permission({**event, "_hook": "PreToolUse"})
            decision = (answer.get("hookSpecificOutput") or {}).get("decision") or {}
            reason = str(decision.get("message", "")) or answer.get("systemMessage", "")
            out: dict = {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                                "permissionDecisionReason": reason},
                         "systemMessage": answer.get("systemMessage", reason)}
            if decision.get("interrupt"):
                out.update({"continue": False, "stopReason": reason})
            return out
        if rules.freeze and result.action_class != "read":
            return self._pre_tool_ask(f"Frozen by policy ({rules.source}): every action asks.")
        if result.action_class in ASK_FIRST:
            key = result.action_class
            # Read without creating the license row: a pass-through or an ask writes nothing.
            lic = agent_repo.effective_license(self.conn, repo, key, principal,
                                               max_level=rules.subagent_max, create=False)
            if min(int(lic["level"]), rules.ceilings[key]) < 1:
                spec = ACTION_CLASSES[key]
                return self._pre_tool_ask(f"{spec.label} always needs a person." if spec.max_level == 0
                                          else f"{spec.label} is at L0 in {repo}: a person decides.")
        if result.mcp_server and policy_mod.tool_ceiling(rules, tool) == 0:
            return self._pre_tool_ask(policy_mod.tool_ask_reason(rules, tool))
        return {}

    @staticmethod
    def _pre_tool_ask(reason: str) -> dict:
        return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "ask",
                                       "permissionDecisionReason": f"Solo License: {reason}"}}

    def permission(self, event: dict) -> dict:
        self._agent = str(event.get("_agent") or "claude-code")
        principal = _principal(event)
        session, cwd = str(event.get("session_id", "")), str(event.get("cwd", "."))
        tool, tool_input = str(event.get("tool_name", "")), event.get("tool_input") or {}
        repo, root = repo_of(cwd)
        turn = self._turn(session, repo, root, principal=principal)
        trace = self._trace(turn)
        command = describe(tool, tool_input)
        result = self._classify(tool, tool_input, root, session=session, repo=repo, principal=principal)
        spec = ACTION_CLASSES[result.action_class]
        rules = policy_mod.effective(self.conn, repo, root)
        lic = agent_repo.effective_license(self.conn, repo, spec.key, principal,
                                           max_level=rules.subagent_max)
        ceiling = policy_mod.ceiling(rules, spec.key, tool)
        level = min(int(lic["level"]), ceiling)
        forbidden = policy_mod.denied(rules, tool, tool_input, root)
        spend = budget.check(self.conn, session, repo, rules.budget)
        subagent_denial = policy_mod.denied_subagent(rules, tool, tool_input)

        if result.hard_deny:
            decision, by, reason = "deny", "hard-deny", f"Blocked: {result.hard_deny}."
        elif subagent_denial:
            decision, by, reason = "deny", "policy", f"Blocked: {subagent_denial}."
        elif forbidden:
            decision, by, reason = "deny", "policy", f"Blocked: {forbidden}."
        elif spend.blocked and spec.key != "read":
            decision, by, reason = "deny", "budget", budget.deny_reason(spend)
        elif rules.freeze:
            by = "license" if event.get("_prompt_only", True) else "agent-settings"
            decision, reason = "ask", f"Frozen by policy ({rules.source}): every action asks."
        elif result.source == "jev" and result.confidence < jev.MIN_CHOICE_CONFIDENCE or (
                result.irreversible is not None
                and jev.GREY_ZONE[0] <= result.irreversible <= jev.GREY_ZONE[1]):
            decision, by, reason = "ask", "classifier", "Not sure what this command does; a person decides."
        elif level >= 2:
            decision, by, reason = "allow", "license", f"{spec.label} is earned at L2 in {repo}."
        elif level >= 1 and agent_repo.pattern_approved(self.conn, repo, result.pattern):
            decision, by, reason = "allow", "license", f"'{result.pattern}' is earned at L1 in {repo}."
        else:
            # Claude Code / Codex only call this when they would prompt a person;
            # other agents call it for every action and keep their own settings.
            by = "license" if event.get("_prompt_only", True) else "agent-settings"
            decision, reason = "ask", (policy_mod.tool_ask_reason(rules, tool)
                                       or self._ask_reason(spec.key, level, lic, ceiling))
        # Counted when calls run (tool_result); here only read, so nothing counts twice.
        repeats = loops.seen(self.conn, session, loops.fingerprint(tool, tool_input)).count + 1
        halted = loops.halted(self.conn, session)
        if decision != "deny" and (repeats >= loops.STOP_AT or halted):
            decision, by = "deny", "loop-guard"
            reason = (halted or remediation.compose("loop-stop", command=command, attempts=repeats).text
                      ).removeprefix("Solo License: ")

        decision_id = agent_repo.insert_decision(
            self.conn, session_id=session, agent=str(event.get("_agent") or "claude-code"), principal=principal,
            turn_id=turn["id"], repo=repo, tool_name=tool,
            action_class=spec.key, pattern=result.pattern, command=command, decision=decision,
            decided_by=by, level=level, source=result.source, reason=reason,
            outcome="denied" if decision == "deny" else "pending", trace_id=trace.trace_id,
        )
        via = {"hook": str(event["_hook"])} if event.get("_hook") else {}
        trace.span(f"gate.{decision}", status="error" if decision == "deny" else "ok",
                   decision_id=decision_id, tool=tool, command=command, action_class=spec.key,
                   pattern=result.pattern, level=level, decided_by=by, source=result.source, reason=reason,
                   policy=rules.digest, policy_source=rules.source, ceiling=ceiling, **result.mcp_attributes, **via)
        if decision == "deny" and by == "policy":
            # As serious as a hard deny: recorded, and the class goes back to asking.
            trace.span("detection.policy_violation", status="error", severity="critical", message=reason,
                       reason=reason, action_class=spec.key, command=command, policy=rules.digest,
                       **result.mcp_attributes, **via)
            self._fail(repo, spec.key, f"Tried an action this repo's policy forbids: {command}", trace, turn=turn,
                       principal=principal)
        elif decision == "deny" and by == "loop-guard":
            # A halt, not evidence: the class keeps its level.
            trace.span("detection.loop", status="error", severity="critical", message=reason, reason=reason,
                       kind="loop-stop", action_class=spec.key, command=command, repeats=repeats, interrupt=True,
                       **via)
            self.conn.commit()
            return self._permission_response(decision, reason, interrupt=True)
        elif decision == "deny" and by == "budget":
            # A stop, not evidence: no level changes.
            self._budget_capped(turn, spend, trace)
        elif decision == "deny":
            trace.span("detection.forbidden_action", status="error", severity="critical",
                       message=reason, reason=reason, action_class=spec.key, command=command, **via)
            self._fail(repo, spec.key, f"Tried a forbidden action: {command}", trace, turn=turn,
                       principal=principal)
        interrupt = False
        if decision == "deny":
            denials = sum(1 for d in agent_repo.decisions_for_turn(self.conn, turn["id"]) if d["decision"] == "deny")
            if denials >= INTERRUPT_AFTER_DENIALS:
                interrupt = True
                text = remediation.compose("denied", reason=reason, attempts=denials).text
                agent_repo.queue_remediation(self.conn, session_id=session, turn_id=turn["id"], kind="denied",
                                             text=text, delivered=True)
                reason = text.removeprefix("Solo License: ")
                trace.span("remediation.sent", status="error", kind="denied", decision_id=decision_id,
                           attempts=denials, action_class=spec.key, reason=reason, interrupt=True, **via)
        self.conn.commit()
        return self._permission_response(decision, reason, interrupt=interrupt)

    def tool_result(self, event: dict, *, failed: bool) -> dict:
        session = str(event.get("session_id", ""))
        tool, tool_input = str(event.get("tool_name", "")), event.get("tool_input") or {}
        principal = _principal(event)
        loop_note, halt = self._watch_loops(session, tool, tool_input, event, failed, principal=principal)
        row = agent_repo.pending_decision(self.conn, session, tool, describe(tool, tool_input),
                                          principal=principal)
        loop_note = "\n\n".join(t for t in (loop_note, self._budget_note(event)) if t)
        if row is None:  # never went through the gate (already allowed by settings)
            self.conn.commit()
            return self._with_loop_note({}, loop_note, halt, failed)
        turn = agent_repo.current_turn(self.conn, session, principal=principal)
        trace = self._trace(turn)
        repo, key = row["repo"], row["action_class"]
        # Trust only grows from a person's yes or from the gate's own earned
        # "allow". An action the *agent's* settings let through (its hook fires
        # on every call, so nobody was asked) is observed, never credited.
        unattended = row["decision"] == "ask" and row["decided_by"] == "agent-settings"
        if row["decision"] == "ask" and not unattended:  # it ran, so the person said yes
            agent_repo.approve_pattern(self.conn, repo, key, row["pattern"])
            agent_repo.set_outcome(self.conn, row["id"], "pending", decided_by="person")
            trace.span("gate.approved_by_person", decision_id=row["id"], pattern=row["pattern"], action_class=key)
        error = str(event.get("error", ""))[:300]
        answer: dict = {}
        diagnostic = key in DIAGNOSTIC or self._mcp_read(repo, tool)
        if failed and not diagnostic and not event.get("is_interrupt"):
            # A failure always counts, whoever let the action run.
            agent_repo.set_outcome(self.conn, row["id"], "failed")
            trace.span("tool.failed", status="error", decision_id=row["id"], action_class=key, error=error)
            why = f"{row['command']} failed: {error.splitlines()[0] if error else 'error'}"
            was = self._fail(repo, key, why, trace, turn=turn, principal=row["principal"])
            checkpoint = self._checkpoint_for(turn) if was > 0 else None
            answer = self._remedy_failed_tool(row, tool_input, demoted=was > 0, trace=trace, reason=why,
                                              level=was, checkpoint=checkpoint)
        elif unattended:
            agent_repo.set_outcome(self.conn, row["id"], "observed")
            trace.span("tool.observed", decision_id=row["id"], action_class=key,
                       note="ran under the agent's own settings; not credited")
        elif diagnostic:
            agent_repo.set_outcome(self.conn, row["id"], "verified")
            trace.span("tool.ran", decision_id=row["id"], action_class=key, exit="error" if failed else "ok")
            self._succeed(repo, key, trace, principal=row["principal"])
        else:  # changed the repo: evidence once the turn's checks pass
            agent_repo.set_outcome(self.conn, row["id"], "ran")
            trace.span("tool.ran", decision_id=row["id"], action_class=key, exit="ok")
        self.conn.commit()
        return self._with_loop_note(answer, loop_note, halt, failed)

    def _watch_loops(self, session: str, tool: str, tool_input: dict, event: dict,
                     failed: bool, *, principal: str = "main") -> tuple[str, bool]:
        """Count a call that ran; (guidance for the agent or "", halt it)."""
        if event.get("is_interrupt"):
            return "", False
        turn = agent_repo.current_turn(self.conn, session, principal=principal)
        if loops.is_edit(tool):
            loops.record_edit(self.conn, session, turn["id"] if turn else None, edited_path(tool_input))
        seen = loops.record(self.conn, session, loops.fingerprint(tool, tool_input), failed=failed,
                            error=str(event.get("error", "")))
        command = describe(tool, tool_input)
        if seen.count >= loops.STOP_AT:
            kind, halt = "loop-stop", True
        elif failed and seen.failures >= loops.SAME_FAILURE_AT:
            kind, halt = "same-failure", False
        elif seen.count >= loops.WARN_AT:
            kind, halt = "repeat", False
        else:
            return "", False
        text = remediation.compose(kind, command=command, reason=seen.error, attempts=seen.count).text
        if halt:
            loops.halt(self.conn, session, text)
        self._trace(turn).span("detection.loop", status="error", severity="critical" if halt else "warning",
                               kind=kind, command=command, repeats=seen.count, failures=seen.failures,
                               action_class=classify_tool(tool, tool_input).action_class,
                               reason=text.removeprefix("Solo License: "), interrupt=halt)
        return text, halt

    @staticmethod
    def _with_loop_note(answer: dict, note: str, halt: bool, failed: bool) -> dict:
        if not note:
            return answer
        out = answer.setdefault("hookSpecificOutput", {
            "hookEventName": "PostToolUseFailure" if failed else "PostToolUse"})
        out["additionalContext"] = "\n\n".join(t for t in (out.get("additionalContext"), note) if t)
        if halt:  # nobody was asked before this run, so stop the agent after it
            answer.update({"continue": False, "stopReason": note})
        return answer

    def _remedy_failed_tool(self, row: sqlite3.Row, tool_input: dict, *, demoted: bool, trace: Trace,
                            reason: str, level: int, checkpoint: str | None) -> dict:
        """Tell the agent, next to the failed tool's result, what to undo. Claude
        Code's PostToolUseFailure takes only ``additionalContext`` (it cannot block)."""
        path = edited_path(tool_input)
        fix = remediation.compose("tool-failed", action_class=row["action_class"], command=row["command"],
                                  files=(path,) if path else (), demoted=demoted, checkpoint=checkpoint)
        delivered = row["agent"] in agents.TAKES_CONTEXT
        if delivered:
            agent_repo.queue_remediation(self.conn, session_id=row["session_id"], turn_id=row["turn_id"],
                                         kind="tool-failed", text=fix.text, delivered=True)
        trace.span("remediation.sent", status="error", kind="tool-failed", decision_id=row["id"],
                   action_class=row["action_class"], revert=list(fix.revert_commands), delivered=delivered,
                   reason=reason, from_level=level, to_level=0 if demoted else level,
                   entire_checkpoint=checkpoint or "")
        return {
            "hookSpecificOutput": {"hookEventName": "PostToolUseFailure", "additionalContext": fix.text},
            "systemMessage": f"Solo License: {row['action_class']} "
                             f"{'is back to asking' if demoted else 'still asks'} after `{row['command']}` failed.",
        }

    def stop(self, event: dict) -> dict:
        session = str(event.get("session_id", ""))
        principal = _principal(event)
        loops.clear_halt(self.conn, session)
        turn = agent_repo.current_turn(self.conn, session, principal=principal)
        if turn is None or turn["status"] != "open":
            self.conn.commit()
            return {}
        trace = self._trace(turn)
        sent_back = self._budget_stop(event, turn, trace, retrying=bool(event.get("stop_hook_active")))
        if sent_back:
            return sent_back
        decisions = agent_repo.decisions_for_turn(self.conn, turn["id"])
        ok, reason, details = (True, "", {})
        if self.verifier is not None:
            ok, reason, details = self.verifier(self, turn, decisions)
        # Cursor reports the files changed by a subagent.  Treat any repository
        # diff outside that declaration as an over-edit, so a parent turn's
        # concurrent changes cannot be credited to the subagent.  Agents that
        # do not provide this field retain the normal snapshot-based check.
        declared_files = event.get("modified_files")
        if principal != "main" and isinstance(declared_files, (list, tuple)):
            declared = {str(path).replace("\\", "/").lstrip("./") for path in declared_files if str(path).strip()}
            actual = {str(path).replace("\\", "/").lstrip("./") for path in self._turn_files(turn)}
            unexpected = sorted(actual - declared)
            if unexpected:
                ok = False
                reason = (f"subagent changed files outside its declared scope: {', '.join(unexpected[:8])}")
                details = {**details, "blame": ["file-edit"], "unexpected_files": unexpected}
        retrying = bool(event.get("stop_hook_active"))
        changed = [d for d in decisions if d["outcome"] == "ran"]
        demoted: list[str] = []
        checkpoint_id = None
        principal = str(turn["principal"] or principal) if turn else principal
        if ok:
            for d in changed:
                agent_repo.set_outcome(self.conn, d["id"], "verified")
                self._succeed(d["repo"], d["action_class"], trace, principal=principal)
        else:
            checkpoint_id = self._checkpoint_for(turn, fresh=True)
            evidence = reason
            if checkpoint_id:
                details["entire_checkpoint"] = checkpoint_id
                evidence = f"{reason}\nEntire: {entire.explain_command(checkpoint_id)}"
            for key in sorted({d["action_class"] for d in changed} | set(details.get("blame", ()))):
                if self._fail(turn["repo"], key, evidence, trace, checkpoint=checkpoint_id,
                              principal=principal) > 0:
                    demoted.append(key)
            for d in changed:
                agent_repo.set_outcome(self.conn, d["id"], "failed")
        measured = {k: v for k, v in details.items() if k != "blame"}
        if not ok and not retrying:
            # Send the agent back to fix it; the turn stays open and is checked again.
            fix = remediation.compose("turn-failed", reason=reason, files=self._turn_files(turn),
                                      base_ref=turn["base_ref"], checkpoint=checkpoint_id, classes=demoted)
            trace.span("turn.blocked", status="error", turn=turn["id"], reason=reason, **measured)
            trace.span("remediation.sent", status="error", kind="turn-failed", turn=turn["id"],
                       revert=list(fix.revert_commands), reason=reason, classes=demoted,
                       entire_checkpoint=checkpoint_id or "")
            agent_repo.note_block(self.conn, turn["id"], reason)
            agent_repo.queue_remediation(self.conn, session_id=session, turn_id=turn["id"], kind="turn-failed",
                                         text=fix.text, delivered=True)
            self.conn.commit()
            return {"decision": "block", "reason": fix.text}
        thrash = loops.thrashed(self.conn, session, turn["id"]) if ok and not retrying else []
        if thrash:
            # Guidance, not evidence: sent back once, no level changes.
            text = remediation.compose("edit-thrash", files=thrash).text
            trace.span("detection.edit_thrash", status="error", severity="warning", turn=turn["id"],
                       files=[p for p, _ in thrash], kind="edit-thrash", action_class="file-edit",
                       reason=text.removeprefix("Solo License: "))
            agent_repo.queue_remediation(self.conn, session_id=session, turn_id=turn["id"], kind="edit-thrash",
                                         text=text, delivered=True)
            self.conn.commit()
            return {"decision": "block", "reason": text}
        for d in decisions:
            if d["outcome"] == "pending":  # left to a person who said no
                agent_repo.set_outcome(self.conn, d["id"], "not-run")
        status = "verified" if ok else "failed"
        # A turn that was sent back once keeps that reason, even once fixed.
        agent_repo.close_turn(self.conn, turn["id"], status=status, reason=reason or turn_reason(self.conn, turn["id"]),
                              **{k: details[k] for k in ("scope_score", "lines_changed", "files_changed", "tests")
                                 if k in details})
        trace.span("turn.end", status="ok" if ok else "error", turn=turn["id"], verdict=status,
                   reason=reason, **measured)
        trace.flush(self.conn, None)
        self._traces.pop(turn["id"], None)
        self.conn.commit()
        return {}

    # --- license changes -------------------------------------------------------

    def _succeed(self, repo: str, key: str, trace: Trace, *, principal: str = "main") -> None:
        lic = agent_repo.effective_license(self.conn, repo, key, principal,
                                           max_level=self._subagent_ceiling(repo, principal))
        explicit = self.conn.execute(
            "SELECT 1 FROM agent_licenses WHERE repo = ? AND principal = ? AND action_class = ?",
            (repo, principal, key),
        ).fetchone()
        if not explicit:
            agent_repo.get_license(self.conn, repo, key, principal=principal)
            if principal != "main" and lic["level"]:
                agent_repo.set_level(self.conn, repo, key, int(lic["level"]), principal=principal)
        agent_repo.add_evidence(self.conn, repo, key, ok=True, principal=principal)
        lic = agent_repo.get_license(self.conn, repo, key, principal=principal)
        target = self.ladder.next_level(key, lic["level"], lic["successes"], lic["failures"],
                                        lic["successes_at_level"],
                                        ceiling=self._subagent_ceiling(repo, principal, key))
        if target is not None:
            self._change(repo, key, "promote", lic["level"], target,
                         f"{lic['successes']} verified, {lic['failures']} failed: the failure rate is below "
                         f"break-even for {ACTION_CLASSES[key].label.lower()} in {repo}.", trace,
                         principal=principal)

    def _fail(self, repo: str, key: str, reason: str, trace: Trace, *, turn: sqlite3.Row | None = None,
              checkpoint: str | None = None, principal: str = "main") -> int:
        """Evidence against a class: back to L0. Returns the level it had. A
        demotion is linked to the turn's Entire checkpoint (looked up only then)."""
        lic = agent_repo.effective_license(self.conn, repo, key, principal,
                                           max_level=self._subagent_ceiling(repo, principal, key))
        agent_repo.add_evidence(self.conn, repo, key, ok=False, principal=principal)
        if lic["level"] > 0:
            self._change(repo, key, "demote", lic["level"], 0, reason, trace,
                         checkpoint=checkpoint or self._checkpoint_for(turn), principal=principal)
        agent_repo.forget_patterns(self.conn, repo, key)
        return int(lic["level"])

    def restore(self, repo: str, key: str, level: int, *, actor_id: str, reason: str,
                principal: str = "main") -> int:
        """A person resumes a paused class at a level they choose (up to its
        principal-aware ceiling under the policy). Recorded like every other
        change."""
        ceiling = self._subagent_ceiling(repo, principal, key)
        level = max(0, min(level, ceiling))
        lic = agent_repo.get_license(self.conn, repo, key, principal=principal)
        trace = self.tracer.start_trace("coding.restore", defaults=_who(repo, principal=principal),
                                        action_class=key, principal=principal)
        self._change(repo, key, "restore", lic["level"], level, f"{actor_id}: {reason}", trace,
                     actor_id=actor_id, principal=principal)
        trace.flush(self.conn, None)
        self.conn.commit()
        return level

    def flag(self, *, decision_id: int | None = None, turn_id: int | None = None, actor_id: str,
             reason: str) -> dict:
        """A person says a decision (or a whole turn) was wrong: its classes go
        back to L0 (a hard reset, not one failure's worth of evidence), approved
        command families are forgotten, and the session's next prompt is told
        what to revert."""
        command, action_class, files = "", "", ()
        if decision_id is not None:
            decision = agent_repo.get_decision(self.conn, decision_id)
            if decision is None:
                raise LookupError(f"No decision {decision_id}.")
            repo, session, turn_id = decision["repo"], decision["session_id"], decision["turn_id"]
            classes = [decision["action_class"]]
            command, action_class = decision["command"], decision["action_class"]
            prefix = f"{decision['tool_name']} "
            if action_class == "file-edit" and command.startswith(prefix):
                files = (command[len(prefix):],)
            turn = agent_repo.get_turn(self.conn, turn_id) if turn_id else None
        elif turn_id is not None:
            turn = agent_repo.get_turn(self.conn, turn_id)
            if turn is None:
                raise LookupError(f"No turn {turn_id}.")
            repo, session = turn["repo"], turn["session_id"]
            ran = {d["action_class"] for d in agent_repo.decisions_for_turn(self.conn, turn_id)
                   if d["outcome"] in FLAGGABLE_OUTCOMES}
            # Edits Claude Code already allows never reach the gate; a turn is still its edits.
            classes = sorted(ran) or ["file-edit"]
            files = tuple(self._turn_files(turn))
        else:
            raise ValueError("Flag a decision or a turn.")

        agent = (decision["agent"] if decision_id is not None else None) or (turn["agent"] if turn else "")
        principal = (decision["principal"] if decision_id is not None else None) or (turn["principal"] if turn else "main")
        checkpoint = turn["entire_checkpoint"] if turn else None
        trace = self.tracer.start_trace("coding.flag", defaults=_who(repo, agent, principal), session_id=session or None)
        for key in classes:
            rules = policy_mod.effective(self.conn, repo, turn["cwd"] if turn else ".")
            lic = agent_repo.effective_license(self.conn, repo, key, principal,
                                               max_level=rules.subagent_max)
            if not self.conn.execute(
                    "SELECT 1 FROM agent_licenses WHERE repo = ? AND principal = ? AND action_class = ?",
                    (repo, principal, key)).fetchone():
                agent_repo.get_license(self.conn, repo, key, principal=principal)
            self._change(repo, key, "flag", lic["level"], 0, f"{actor_id}: {reason}", trace, actor_id=actor_id,
                         checkpoint=checkpoint, principal=principal)
            agent_repo.forget_patterns(self.conn, repo, key)
        fix = remediation.compose("flagged", reason=reason, action_class=action_class, command=command,
                                  files=files, classes=classes, base_ref=turn["base_ref"] if turn else None,
                                  checkpoint=checkpoint)
        remediation_id = agent_repo.queue_remediation(self.conn, session_id=session, turn_id=turn_id,
                                                      kind="flagged", text=fix.text)
        trace.span("remediation.queued", kind="flagged", remediation=remediation_id,
                   action_class=action_class or ",".join(classes), reason=reason, revert=list(fix.revert_commands))
        flag_id = agent_repo.insert_flag(self.conn, decision_id=decision_id, turn_id=turn_id, actor_id=actor_id,
                                         reason=reason, remediation_id=remediation_id)
        trace.span("turn.flagged", status="error", flag=flag_id, decision_id=decision_id or 0, turn=turn_id or 0,
                   classes=classes, actor_id=actor_id, reason=reason, action_class=action_class or ",".join(classes),
                   entire_checkpoint=checkpoint or "", turn_trace_id=(turn["trace_id"] if turn else None) or "")
        trace.flush(self.conn, None)
        self.conn.commit()
        return {"flag_id": flag_id, "repo": repo, "classes": classes, "session_id": session, "text": fix.text}

    def record_policy(self, repo: str, summary: str, actor_id: str) -> str | None:
        """A policy change on this machine: an event, a trace and a ledger commit."""
        trace = self.tracer.start_trace("coding.policy", defaults=_who(repo))
        event_id = agent_repo.insert_event(self.conn, repo=repo, action_class="policy", kind="policy",
                                           from_level=0, to_level=0, reason=summary, actor_id=actor_id,
                                           trace_id=trace.trace_id)
        sha = self.ledger.record(LedgerEntry(f"policy@{repo}", "policy", 0, 0, summary, None, trace.trace_id))
        if sha:
            agent_repo.set_event_sha(self.conn, event_id, sha)
        trace.span("license.policy", action_class="policy", reason=summary, actor_id=actor_id, git_sha=sha or "")
        trace.flush(self.conn, None)
        return sha

    # --- budget ----------------------------------------------------------------

    def _budget_status(self, event: dict, turn: sqlite3.Row) -> budget.Status:
        """Spend so far (re-read from the agent's transcript, if it has one) against the policy's caps."""
        budget.observe(self.conn, event, turn["repo"])
        rules = policy_mod.effective(self.conn, turn["repo"], turn["cwd"])
        return budget.check(self.conn, turn["session_id"], turn["repo"], rules.budget)

    def _budget_note(self, event: dict) -> str:
        """Text for the agent the first time its session crosses the warn line or a cap."""
        turn = agent_repo.current_turn(self.conn, str(event.get("session_id", "")))
        if turn is None:
            return ""
        status = self._budget_status(event, turn)
        note = budget.notice(self.conn, status)
        if note is None:
            return ""
        trace = self._trace(turn)
        if note.kind == "cap":
            self._budget_capped(turn, status, trace)
        else:
            trace.span("detection.budget", status="error", severity="warning", kind="budget-warn",
                       reason=note.text.removeprefix("Solo License: "), spent=status.spent, cap=status.cap,
                       scope=status.scope)
        agent_repo.queue_remediation(self.conn, session_id=turn["session_id"], turn_id=turn["id"],
                                     kind=f"budget-{note.kind}", text=note.text, delivered=True)
        return note.text

    def _budget_stop(self, event: dict, turn: sqlite3.Row, trace: Trace, *, retrying: bool) -> dict:
        """At the cap, a turn is sent back once for a summary instead of more work."""
        status = self._budget_status(event, turn)
        if retrying or not status.blocked or not budget.mark_once(self.conn, f"turn:{turn['id']}", "budget-stop"):
            return {}
        self._budget_capped(turn, status, trace)
        text = budget.stop_text(status)
        trace.span("remediation.sent", status="error", kind="budget-stop", turn=turn["id"],
                   reason=text.removeprefix("Solo License: "), spent=status.spent, cap=status.cap)
        agent_repo.queue_remediation(self.conn, session_id=turn["session_id"], turn_id=turn["id"],
                                     kind="budget-stop", text=text, delivered=True)
        self.conn.commit()
        return {"decision": "block", "reason": text}

    def _budget_capped(self, turn: sqlite3.Row, status: budget.Status, trace: Trace) -> None:
        """The first time a cap is reached: an incident, an event and a ledger commit."""
        if not budget.mark_once(self.conn, status.scope_key, f"recorded@{status.cap}"):
            return
        summary = (f"{status.scope.capitalize()} budget reached: {budget.usd(status.spent)} of "
                   f"{budget.usd(status.cap)} ({turn['agent']}, session {turn['session_id'][:12]}). "
                   "Only reading is allowed until a person raises the cap or resumes.")
        trace.span("detection.budget", status="error", severity="critical", kind="budget-cap", reason=summary,
                   spent=status.spent, cap=status.cap, scope=status.scope)
        self._budget_event(turn["repo"], summary, GATE_ACTOR, trace)

    def resume_budget(self, repo: str, session_id: str | None, *, actor_id: str) -> list[str]:
        """A person lifts the cap for a session (and the repo today), recorded like any change."""
        lifted = budget.resume(self.conn, repo, session_id, actor_id)
        trace = self.tracer.start_trace("coding.budget", defaults=_who(repo), session_id=session_id or None)
        where = f"session {session_id[:12]}" if session_id else "today"
        self._budget_event(repo, f"{actor_id}: resumed past the budget cap for {where} in {repo}.", actor_id, trace)
        trace.flush(self.conn, None)
        self.conn.commit()
        return lifted

    def _budget_event(self, repo: str, summary: str, actor_id: str, trace: Trace) -> None:
        event_id = agent_repo.insert_event(self.conn, repo=repo, action_class="budget", kind="budget", from_level=0,
                                           to_level=0, reason=summary, actor_id=actor_id, trace_id=trace.trace_id)
        sha = self.ledger.record(LedgerEntry(f"budget@{repo}", "budget", 0, 0, summary, None, trace.trace_id))
        if sha:
            agent_repo.set_event_sha(self.conn, event_id, sha)
        trace.span("license.budget", action_class="budget", reason=summary, actor_id=actor_id, git_sha=sha or "")

    def _change(self, repo: str, key: str, kind: str, old: int, new: int, reason: str, trace: Trace,
                actor_id: str = GATE_ACTOR, checkpoint: str | None = None,
                principal: str = "main") -> None:
        lost = kind in ("demote", "flag")
        agent_repo.set_level(self.conn, repo, key, new, demoted_from=old if lost else None, principal=principal)
        event_id = agent_repo.insert_event(self.conn, repo=repo, action_class=key, kind=kind,
                                           from_level=old, to_level=new, reason=reason, actor_id=actor_id,
                                           principal=principal, trace_id=trace.trace_id,
                                           entire_checkpoint=checkpoint)
        sha = self.ledger.record(LedgerEntry(f"{key}@{repo}", kind, old, new, reason, None, trace.trace_id,
                                             entire_checkpoint=checkpoint))
        if sha:
            agent_repo.set_event_sha(self.conn, event_id, sha)
        trace.span(f"license.{kind}", status="error" if lost else "ok", action_class=key,
                   repo=repo, from_level=old, to_level=new, reason=reason, git_sha=sha or "",
                   actor_id=actor_id, principal=principal, entire_checkpoint=checkpoint or "")

    # --- helpers -----------------------------------------------------------

    def _classify(self, tool: str, tool_input: dict, root: str, *, session: str = "", repo: str = "",
                  principal: str = "main") -> Classification:
        result = classify_tool(tool, tool_input)
        if result.action_class != "unknown" or result.hard_deny or not self.jev_client.enabled:
            return result
        session_state = digest.state(self.conn, session, repo=repo, principal=principal,
                                     current_call={"tool": tool, "input": tool_input}) if session else ""
        verdict = jev.classify_command(self.jev_client, describe(tool, tool_input), root,
                                       session_state=session_state)
        if verdict is None:
            return Classification("unknown", result.pattern, "fallback")
        return Classification(verdict.action_class, result.pattern, "jev", verdict.confidence,
                              irreversible=verdict.irreversible)

    def ceiling(self, repo: str, key: str) -> int:
        """This class's highest level in this repo under the effective policy."""
        row = self.conn.execute("SELECT path FROM agent_repos WHERE repo = ?", (repo,)).fetchone()
        rules = policy_mod.effective(self.conn, repo, row["path"] if row else ".")
        return rules.ceilings[key]

    def ceiling_for(self, repo: str, key: str, principal: str = "main") -> int:
        """The policy ceiling for one action and principal."""
        return self._subagent_ceiling(repo, principal, key)

    def _subagent_ceiling(self, repo: str, principal: str, key: str | None = None) -> int:
        """Return the effective ceiling for one principal and action class."""
        row = self.conn.execute("SELECT path FROM agent_repos WHERE repo = ?", (repo,)).fetchone()
        rules = policy_mod.effective(self.conn, repo, row["path"] if row else ".")
        ceiling = rules.subagent_max
        if key is not None:
            ceiling = min(ceiling, rules.ceilings[key])
        return ceiling if principal != "main" else (rules.ceilings[key] if key is not None else 2)
    def _mcp_read(self, repo: str, tool: str) -> bool:
        """An MCP read (list_issues) is like ``read``: it changes nothing, so it
        counts as soon as it ran and a failure is information, not a mistake."""
        if not tool.startswith("mcp__"):
            return False
        row = self.conn.execute("SELECT path FROM agent_repos WHERE repo = ?", (repo,)).fetchone()
        return policy_mod.tool_risk(policy_mod.effective(self.conn, repo, row["path"] if row else "."), tool) == "read"

    def _ask_reason(self, key: str, level: int, lic: sqlite3.Row, ceiling: int | None = None) -> str:
        spec = ACTION_CLASSES[key]
        if spec.max_level == 0:
            return f"{spec.label} always needs a person."
        if ceiling == 0:
            return f"{spec.label} always asks in this repo (policy)."
        progress = self.ladder.progress(key, level, lic["successes"], lic["failures"], lic["successes_at_level"],
                                        ceiling=ceiling)
        needed = progress["runs_needed"]
        more = f"{needed} more verified run{'s' if needed != 1 else ''}" if needed else "a person's approval"
        return f"{spec.label} is at L{level}; {more} to earn L{level + 1}."

    @staticmethod
    def _permission_response(decision: str, reason: str, *, interrupt: bool = False) -> dict:
        if decision == "ask":
            return {"systemMessage": f"Solo License: {reason}"}
        body: dict = {"behavior": decision}
        if decision == "deny" and interrupt:
            body.update(message=f"Solo License: {reason}", interrupt=True)
        elif decision == "deny":
            body["message"] = f"Solo License: {reason} Choose a safer way to do this."
        return {
            "hookSpecificOutput": {"hookEventName": "PermissionRequest", "decision": body},
            "systemMessage": f"Solo License: {reason}",
        }

    @staticmethod
    def _turn_files(turn: sqlite3.Row) -> list[str]:
        """Files this turn changed against its starting snapshot."""
        from sololicense.coding.verify import changed_files

        try:
            started = datetime.strptime(turn["created_at"], "%Y-%m-%d %H:%M:%S").replace(
                tzinfo=timezone.utc).timestamp() - 1
        except (TypeError, ValueError):
            started = None
        return [c.path for c in changed_files(turn["cwd"], turn["base_ref"], since=started)]

    def _turn(self, session: str, repo: str, root: str, *, principal: str = "main") -> sqlite3.Row:
        turn = agent_repo.current_turn(self.conn, session, principal=principal)
        if turn is None or turn["status"] != "open":
            self.user_prompt({"session_id": session, "cwd": root, "prompt": "", "_agent": self._agent,
                              "_principal": principal,
                              "_implicit": True})
            turn = agent_repo.current_turn(self.conn, session, principal=principal)
        return turn

    def _trace(self, turn: sqlite3.Row | None) -> Trace:
        if turn is not None and turn["id"] in self._traces:
            return self._traces[turn["id"]]
        if turn is None:
            return self.tracer.start_trace("coding.turn", resumed=True)
        trace = self.tracer.start_trace("coding.turn", defaults=_who(turn["repo"], turn["agent"], turn["principal"]),
                                        session_id=turn["session_id"] or None, resumed=True)
        self._traces[turn["id"]] = trace
        return trace

    def _checkpoint_for(self, turn: sqlite3.Row | None, *, fresh: bool = False) -> str | None:
        """The agent's last Entire checkpoint for this turn, looked up once and
        kept on the turn (``fresh`` looks again, keeping the old one if none)."""
        if turn is None:
            return None
        row = agent_repo.get_turn(self.conn, turn["id"])
        if row is None:
            return None
        if row["entire_checkpoint"] and not fresh:
            return row["entire_checkpoint"]
        found = self.checkpoint_lookup(row["cwd"], row["session_id"])
        checkpoint_id = str((found or {}).get("checkpoint_id") or "")
        if checkpoint_id:
            agent_repo.set_checkpoint(self.conn, row["id"], checkpoint_id)
            return checkpoint_id
        return row["entire_checkpoint"] or None
