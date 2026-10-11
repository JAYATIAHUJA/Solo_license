"""The coding-agent gate: Claude Code hook events in, license decisions out.

Claude Code calls three of its hooks over HTTP; the agent cannot skip them:

* ``UserPromptSubmit`` opens a *turn*: the request and a snapshot of the
  working tree, so the end of the turn can be checked against both.
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
from pathlib import Path
from typing import Callable

from sololicense.coding import entire, jev
from sololicense.coding import policy as policy_mod
from sololicense.coding.actions import ACTION_CLASSES, Classification, classify_tool, describe
from sololicense.coding.ladder import CodingLadder
from sololicense.db.repositories import agent as agent_repo
from sololicense.observability.tracer import Trace, Tracer
from sololicense.services.git_ledger import GitLedger, LedgerEntry

# Classes whose non-zero exit is information, not a mistake: a failing test
# run is the agent doing its job.
DIAGNOSTIC = {"read", "test-run", "lint-format", "build"}
GATE_ACTOR = "system:coding-gate"


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
        trace = self.tracer.start_trace("coding.turn", repo=repo, session=session[:12], agent=agent)
        turn_id = agent_repo.open_turn(
            self.conn, session_id=session, repo=repo, cwd=root,
            prompt=str(event.get("prompt", ""))[:8000], base_ref=snapshot(root), trace_id=trace.trace_id,
            agent=agent,
        )
        self._traces[turn_id] = trace
        trace.span("turn.start", turn=turn_id, prompt=str(event.get("prompt", ""))[:300])
        self.conn.commit()
        return {}

    def permission(self, event: dict) -> dict:
        self._agent = str(event.get("_agent") or "claude-code")
        session, cwd = str(event.get("session_id", "")), str(event.get("cwd", "."))
        tool, tool_input = str(event.get("tool_name", "")), event.get("tool_input") or {}
        repo, root = repo_of(cwd)
        turn = self._turn(session, repo, root)
        trace = self._trace(turn)
        command = describe(tool, tool_input)
        result = self._classify(tool, tool_input, root)
        spec = ACTION_CLASSES[result.action_class]
        lic = agent_repo.get_license(self.conn, repo, spec.key)
        rules = policy_mod.effective(self.conn, repo, root)
        ceiling = rules.ceilings[spec.key]
        level = min(int(lic["level"]), ceiling)
        forbidden = policy_mod.denied(rules, tool, tool_input, root)

        if result.hard_deny:
            decision, by, reason = "deny", "hard-deny", f"Blocked: {result.hard_deny}."
        elif forbidden:
            decision, by, reason = "deny", "policy", f"Blocked: {forbidden}."
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
            decision, reason = "ask", self._ask_reason(spec.key, level, lic, ceiling)

        decision_id = agent_repo.insert_decision(
            self.conn, session_id=session, agent=str(event.get("_agent") or "claude-code"),
            turn_id=turn["id"], repo=repo, tool_name=tool,
            action_class=spec.key, pattern=result.pattern, command=command, decision=decision,
            decided_by=by, level=level, source=result.source, reason=reason,
            outcome="denied" if decision == "deny" else "pending", trace_id=trace.trace_id,
        )
        trace.span(f"gate.{decision}", status="error" if decision == "deny" else "ok",
                   decision_id=decision_id, tool=tool, command=command, action_class=spec.key,
                   pattern=result.pattern, level=level, decided_by=by, source=result.source, reason=reason,
                   policy=rules.digest, policy_source=rules.source, ceiling=ceiling)
        if decision == "deny" and by == "policy":
            # As serious as a hard deny: recorded, and the class goes back to asking.
            trace.span("detection.policy_violation", status="error", severity="critical",
                       message=reason, action_class=spec.key, command=command, policy=rules.digest)
            self._fail(repo, spec.key, f"Tried an action this repo's policy forbids: {command}", trace)
        elif decision == "deny":
            trace.span("detection.forbidden_action", status="error", severity="critical",
                       message=reason, action_class=spec.key, command=command)
            self._fail(repo, spec.key, f"Tried a forbidden action: {command}", trace)
        self.conn.commit()
        return self._permission_response(decision, reason)

    def tool_result(self, event: dict, *, failed: bool) -> dict:
        session = str(event.get("session_id", ""))
        tool, tool_input = str(event.get("tool_name", "")), event.get("tool_input") or {}
        row = agent_repo.pending_decision(self.conn, session, tool, describe(tool, tool_input))
        if row is None:  # never went through the gate (already allowed by settings)
            return {}
        trace = self._trace(agent_repo.current_turn(self.conn, session))
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
        if failed and key not in DIAGNOSTIC and not event.get("is_interrupt"):
            # A failure always counts, whoever let the action run.
            agent_repo.set_outcome(self.conn, row["id"], "failed")
            trace.span("tool.failed", status="error", decision_id=row["id"], action_class=key, error=error)
            self._fail(repo, key, f"{row['command']} failed: {error.splitlines()[0] if error else 'error'}", trace)
        elif unattended:
            agent_repo.set_outcome(self.conn, row["id"], "observed")
            trace.span("tool.observed", decision_id=row["id"], action_class=key,
                       note="ran under the agent's own settings; not credited")
        elif key in DIAGNOSTIC:
            agent_repo.set_outcome(self.conn, row["id"], "verified")
            trace.span("tool.ran", decision_id=row["id"], action_class=key, exit="error" if failed else "ok")
            self._succeed(repo, key, trace)
        else:  # changed the repo: evidence once the turn's checks pass
            agent_repo.set_outcome(self.conn, row["id"], "ran")
            trace.span("tool.ran", decision_id=row["id"], action_class=key, exit="ok")
        self.conn.commit()
        return {}

    def stop(self, event: dict) -> dict:
        session = str(event.get("session_id", ""))
        turn = agent_repo.current_turn(self.conn, session)
        if turn is None or turn["status"] != "open":
            return {}
        trace = self._trace(turn)
        decisions = agent_repo.decisions_for_turn(self.conn, turn["id"])
        ok, reason, details = (True, "", {})
        if self.verifier is not None:
            ok, reason, details = self.verifier(self, turn, decisions)
        retrying = bool(event.get("stop_hook_active"))
        changed = [d for d in decisions if d["outcome"] == "ran"]
        if ok:
            for d in changed:
                agent_repo.set_outcome(self.conn, d["id"], "verified")
                self._succeed(d["repo"], d["action_class"], trace)
        else:
            checkpoint = self.checkpoint_lookup(turn["cwd"], session)
            evidence = reason
            if checkpoint and checkpoint.get("checkpoint_id"):
                details["entire_checkpoint"] = checkpoint["checkpoint_id"]
                agent_repo.set_checkpoint(self.conn, turn["id"], checkpoint["checkpoint_id"])
                evidence = f"{reason}\nEntire: {entire.explain_command(checkpoint['checkpoint_id'])}"
            for key in sorted({d["action_class"] for d in changed} | set(details.get("blame", ()))):
                self._fail(turn["repo"], key, evidence, trace)
            for d in changed:
                agent_repo.set_outcome(self.conn, d["id"], "failed")
        measured = {k: v for k, v in details.items() if k != "blame"}
        if not ok and not retrying:
            # Send the agent back to fix it; the turn stays open and is checked again.
            trace.span("turn.blocked", status="error", turn=turn["id"], reason=reason, **measured)
            agent_repo.note_block(self.conn, turn["id"], reason)
            self.conn.commit()
            return {"decision": "block", "reason": f"Solo License: {reason}"}
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

    def _succeed(self, repo: str, key: str, trace: Trace) -> None:
        agent_repo.add_evidence(self.conn, repo, key, ok=True)
        lic = agent_repo.get_license(self.conn, repo, key)
        target = self.ladder.next_level(key, lic["level"], lic["successes"], lic["failures"],
                                        lic["successes_at_level"], ceiling=self.ceiling(repo, key))
        if target is not None:
            self._change(repo, key, "promote", lic["level"], target,
                         f"{lic['successes']} verified, {lic['failures']} failed: the failure rate is below "
                         f"break-even for {ACTION_CLASSES[key].label.lower()} in {repo}.", trace)

    def _fail(self, repo: str, key: str, reason: str, trace: Trace) -> None:
        agent_repo.add_evidence(self.conn, repo, key, ok=False)
        lic = agent_repo.get_license(self.conn, repo, key)
        if lic["level"] > 0:
            self._change(repo, key, "demote", lic["level"], 0, reason, trace)
        agent_repo.forget_patterns(self.conn, repo, key)

    def restore(self, repo: str, key: str, level: int, *, actor_id: str, reason: str) -> int:
        """A person resumes a paused class at a level they choose (up to its
        ceiling under the policy). Recorded like every other change."""
        level = max(0, min(level, self.ceiling(repo, key)))
        lic = agent_repo.get_license(self.conn, repo, key)
        trace = self.tracer.start_trace("coding.restore", repo=repo, action_class=key)
        self._change(repo, key, "restore", lic["level"], level, f"{actor_id}: {reason}", trace, actor_id=actor_id)
        trace.flush(self.conn, None)
        self.conn.commit()
        return level

    def record_policy(self, repo: str, summary: str, actor_id: str) -> str | None:
        """A policy change on this machine: an event and a ledger commit."""
        event_id = agent_repo.insert_event(self.conn, repo=repo, action_class="policy", kind="policy",
                                           from_level=0, to_level=0, reason=summary, actor_id=actor_id)
        sha = self.ledger.record(LedgerEntry(f"policy@{repo}", "policy", 0, 0, summary, None, None))
        if sha:
            agent_repo.set_event_sha(self.conn, event_id, sha)
        return sha

    def _change(self, repo: str, key: str, kind: str, old: int, new: int, reason: str, trace: Trace,
                actor_id: str = GATE_ACTOR) -> None:
        agent_repo.set_level(self.conn, repo, key, new, demoted_from=old if kind == "demote" else None)
        event_id = agent_repo.insert_event(self.conn, repo=repo, action_class=key, kind=kind,
                                           from_level=old, to_level=new, reason=reason, actor_id=actor_id)
        sha = self.ledger.record(LedgerEntry(f"{key}@{repo}", kind, old, new, reason, None, trace.trace_id))
        if sha:
            agent_repo.set_event_sha(self.conn, event_id, sha)
        trace.span(f"license.{kind}", status="error" if kind == "demote" else "ok", action_class=key,
                   repo=repo, from_level=old, to_level=new, reason=reason, git_sha=sha or "")

    # --- helpers -----------------------------------------------------------

    def _classify(self, tool: str, tool_input: dict, root: str) -> Classification:
        result = classify_tool(tool, tool_input)
        if result.action_class != "unknown" or result.hard_deny or not self.jev_client.enabled:
            return result
        verdict = jev.classify_command(self.jev_client, describe(tool, tool_input), root)
        if verdict is None:
            return Classification("unknown", result.pattern, "fallback")
        return Classification(verdict.action_class, result.pattern, "jev", verdict.confidence,
                              irreversible=verdict.irreversible)

    def ceiling(self, repo: str, key: str) -> int:
        """This class's highest level in this repo under the effective policy."""
        row = self.conn.execute("SELECT path FROM agent_repos WHERE repo = ?", (repo,)).fetchone()
        rules = policy_mod.effective(self.conn, repo, row["path"] if row else ".")
        return rules.ceilings[key]

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
    def _permission_response(decision: str, reason: str) -> dict:
        if decision == "ask":
            return {"systemMessage": f"Solo License: {reason}"}
        body = {"behavior": decision}
        if decision == "deny":
            body["message"] = f"Solo License: {reason} Choose a safer way to do this."
        return {
            "hookSpecificOutput": {"hookEventName": "PermissionRequest", "decision": body},
            "systemMessage": f"Solo License: {reason}",
        }

    def _turn(self, session: str, repo: str, root: str) -> sqlite3.Row:
        turn = agent_repo.current_turn(self.conn, session)
        if turn is None or turn["status"] != "open":
            self.user_prompt({"session_id": session, "cwd": root, "prompt": "", "_agent": self._agent})
            turn = agent_repo.current_turn(self.conn, session)
        return turn

    def _trace(self, turn: sqlite3.Row | None) -> Trace:
        if turn is not None and turn["id"] in self._traces:
            return self._traces[turn["id"]]
        trace = self.tracer.start_trace("coding.turn", resumed=True)
        if turn is not None:
            self._traces[turn["id"]] = trace
        return trace
