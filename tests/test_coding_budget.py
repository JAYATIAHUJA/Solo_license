"""Budget guardrails: spend is read per agent, caps are enforced through the
same gate paths for every agent (pre-tool deny, post-tool context, Stop send-back)."""

from __future__ import annotations

import json
import subprocess

import pytest

from sololicense.coding import agents, budget, policy
from sololicense.coding.gate import CodingGate
from sololicense.coding.jev import JevClient
from sololicense.db.database import apply_schema
from sololicense.services.git_ledger import GitLedger


def _git_init(path):
    path.mkdir()
    for args in (["init", "-q"], ["config", "user.name", "Test"], ["config", "user.email", "t@example.com"]):
        subprocess.run(["git", *args], cwd=path, check=True)
    (path / "app.py").write_text("print('hi')\n")
    subprocess.run(["git", "add", "."], cwd=path, check=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=path, check=True)
    return path


@pytest.fixture
def gate(harness, tmp_path):
    project = _git_init(tmp_path / "shop-api")
    gate = CodingGate(harness.conn, harness.tracer, GitLedger(repo_root=harness.repo),
                      jev_client=JevClient(), checkpoint_lookup=lambda cwd, session: None)
    gate.project = project
    gate.transcript = tmp_path / "claude-session.jsonl"
    policy.save_local(harness.conn, "*", {"budget": {"session_usd": 1.0, "day_usd": 5.0, "warn_at": 0.8}})
    harness.conn.commit()
    return gate


def _event(gate, **fields):
    return {"session_id": "s1", "cwd": str(gate.project), "transcript_path": str(gate.transcript), **fields}


def _bash(gate, command, **fields):
    return _event(gate, tool_name="Bash", tool_input={"command": command}, **fields)


def _spend_output_tokens(gate, msg_id, tokens):
    """Append one Sonnet message to the Claude transcript ($15 per million output tokens)."""
    line = {"type": "assistant", "message": {"id": msg_id, "model": "claude-sonnet-4-5", "usage": {
        "input_tokens": 0, "output_tokens": tokens}}}
    with gate.transcript.open("a", encoding="utf-8") as f:
        f.write(json.dumps(line) + "\n")


def _context(answer):
    return (answer.get("hookSpecificOutput") or {}).get("additionalContext", "")


def _spans(gate, name):
    return [s for t in gate._traces.values() for s in t.spans if s.name == name]


def test_warn_then_cap_then_deny_then_send_back_then_resume(gate):
    gate.user_prompt(_event(gate, prompt="refactor the cart"))

    _spend_output_tokens(gate, "m1", 56_000)          # $0.84 of $1.00
    warn = gate.tool_result(_bash(gate, "npm test"), failed=False)
    assert "Be concise" in _context(warn) and "$0.84" in _context(warn)
    assert _context(gate.tool_result(_bash(gate, "npm run lint"), failed=False)) == ""   # once

    _spend_output_tokens(gate, "m2", 20_000)          # $1.14
    capped = gate.tool_result(_bash(gate, "npm run build"), failed=False)
    assert "budget of $1.00 is used up" in _context(capped)
    [event] = gate.conn.execute("SELECT * FROM agent_events WHERE kind = 'budget'").fetchall()
    assert event["action_class"] == "budget" and event["git_sha"] and "Session budget reached" in event["reason"]
    [incident] = [s for s in _spans(gate, "detection.budget") if s.attributes.get("severity") == "critical"]
    assert incident.attributes["incident"] is True

    denied = gate.pre_tool(_bash(gate, "npm install left-pad"))["hookSpecificOutput"]
    assert denied["permissionDecision"] == "deny" and "Budget reached" in denied["permissionDecisionReason"]
    assert gate.pre_tool(_event(gate, tool_name="Read", tool_input={"file_path": "app.py"})) == {}
    levels = gate.conn.execute("SELECT MAX(level) AS l FROM agent_licenses").fetchone()["l"]
    assert not levels  # a budget stop is not evidence against any class

    back = gate.stop(_event(gate))
    assert back["decision"] == "block" and "short summary" in back["reason"]
    assert gate.stop(_event(gate, stop_hook_active=True)) == {}
    assert gate.conn.execute("SELECT COUNT(*) AS n FROM agent_events WHERE kind = 'budget'").fetchone()["n"] == 1

    gate.resume_budget("shop-api", "s1", actor_id="demo:jayati")
    gate.user_prompt(_event(gate, prompt="go on"))
    assert gate.pre_tool(_bash(gate, "npm install left-pad")) == {}
    resumed = gate.conn.execute("SELECT * FROM agent_events WHERE kind = 'budget' ORDER BY id DESC").fetchone()
    assert resumed["actor_id"] == "demo:jayati" and "resumed" in resumed["reason"]


def _native(gate, agent, native_event, payload):
    event, body = agents.normalize(agent, native_event, payload)
    body.update(_agent=agent, _prompt_only=False)
    if event == agents.PROMPT:
        answer = gate.user_prompt(body)
    elif event == agents.PERMISSION:
        answer = gate.permission(body)
    elif event == agents.STOP:
        answer = gate.stop(body)
    else:
        answer = gate.tool_result(body, failed=event == agents.POST_FAIL)
    return agents.render(agent, native_event, answer)


def test_todays_repo_cap_stops_every_agent_in_their_own_words(gate):
    """Claude Code spent today's budget in this repo: any other agent there is stopped too."""
    budget.record(gate.conn, session_id="claude-1", agent="claude-code", repo="shop-api", part="statusline",
                  spend=budget.Spend(reported_usd=5.5))
    cwd = str(gate.project)

    codex = _native(gate, "codex", "PermissionRequest",
                    {"session_id": "cx", "cwd": cwd, "tool_name": "Bash", "tool_input": {"command": "rm -rf build"}})
    decision = codex.body["hookSpecificOutput"]["decision"]
    assert decision["behavior"] == "deny" and "today's $5.00 cap" in decision["message"]

    cursor = _native(gate, "cursor", "beforeShellExecution",
                     {"conversation_id": "cu", "workspace_roots": [cwd], "command": "npm publish"})
    assert cursor.body["permission"] == "deny"

    windsurf = _native(gate, "windsurf", "pre_run_command",
                       {"trajectory_id": "ws", "tool_info": {"command_line": "make deploy", "cwd": cwd}})
    assert windsurf.exit == 2 and "Budget reached" in windsurf.stderr

    opencode = _native(gate, "opencode", "tool.execute.before",
                       {"sessionID": "oc", "cwd": cwd, "tool_name": "write", "tool_input": {"filePath": "a.py"}})
    assert opencode.body["decision"] == "deny"

    gemini_read = _native(gate, "gemini", "BeforeTool",
                          {"session_id": "ge", "cwd": cwd, "tool_name": "read_file", "tool_input": {"path": "a.py"}})
    assert gemini_read.exit == 0


def test_send_back_at_the_cap_reaches_agents_that_can_continue(gate):
    budget.record(gate.conn, session_id="cx", agent="codex", repo="shop-api", part="transcript",
                  spend=budget.Spend(reported_usd=2.0))
    cwd = str(gate.project)
    _native(gate, "codex", "UserPromptSubmit", {"session_id": "cx", "cwd": cwd, "prompt": "go"})

    stop = _native(gate, "codex", "Stop", {"session_id": "cx", "cwd": cwd})
    assert stop.body["decision"] == "block" and "short summary" in stop.body["reason"]


def test_codex_spend_is_read_from_the_rollout_its_hooks_name(gate, tmp_path):
    rollout = tmp_path / "rollout-2026-10-12T10-00-00-cx.jsonl"
    rollout.write_text("\n".join(json.dumps(r) for r in (
        {"type": "turn_context", "payload": {"model": "gpt-5-codex"}},
        {"type": "event_msg", "payload": {"type": "token_count", "info": {"total_token_usage": {
            "input_tokens": 100_000, "cached_input_tokens": 80_000, "output_tokens": 20_000}}}},
    )) + "\n", encoding="utf-8")
    cwd = str(gate.project)
    _native(gate, "codex", "UserPromptSubmit", {"session_id": "cx", "cwd": cwd, "prompt": "go",
                                                "transcript_path": str(rollout)})

    _native(gate, "codex", "PostToolUse", {"session_id": "cx", "cwd": cwd, "transcript_path": str(rollout),
                                           "tool_name": "Bash", "tool_input": {"command": "ls"},
                                           "tool_response": {"exit_code": 0}})

    spent = budget.session_spend(gate.conn, "cx")
    assert spent.source == budget.ESTIMATE and spent.agent == "codex"
    assert spent.usd == pytest.approx((20_000 * 1.25 + 80_000 * 0.125 + 20_000 * 10) / 1e6)


def test_a_reported_cost_replaces_the_estimate_and_today_follows(gate):
    estimate = budget.Spend()
    estimate.add("claude-sonnet-4-5", budget.Tokens(output=100_000))   # $1.50
    budget.record(gate.conn, session_id="s9", agent="claude-code", repo="shop-api", part="transcript", spend=estimate)
    assert budget.day_spend(gate.conn, "shop-api") == pytest.approx(1.5)

    budget.record(gate.conn, session_id="s9", agent="claude-code", repo="shop-api", part="statusline",
                  spend=budget.Spend(reported_usd=1.2))
    spent = budget.session_spend(gate.conn, "s9")
    assert (spent.usd, spent.source, spent.tokens) == (1.2, budget.REPORTED, 100_000)
    assert budget.day_spend(gate.conn, "shop-api") == pytest.approx(1.2)

    budget.record(gate.conn, session_id="s9", agent="claude-code", repo="shop-api", part="statusline",
                  spend=budget.Spend(reported_usd=1.2))
    assert budget.day_spend(gate.conn, "shop-api") == pytest.approx(1.2)   # re-reporting changes nothing


def test_no_caps_means_no_stops(harness, tmp_path):
    project = _git_init(tmp_path / "free")
    gate = CodingGate(harness.conn, harness.tracer, GitLedger(repo_root=harness.repo), jev_client=JevClient(),
                      checkpoint_lookup=lambda cwd, session: None)
    budget.record(harness.conn, session_id="s1", agent="claude-code", repo="free", part="statusline",
                  spend=budget.Spend(reported_usd=500))
    event = {"session_id": "s1", "cwd": str(project), "tool_name": "Bash", "tool_input": {"command": "npm test"}}
    assert gate.pre_tool(event) == {}


# --- policy ------------------------------------------------------------------------

def test_budget_in_the_team_file_and_the_machine_merge_to_the_strictest(gate):
    (gate.project / ".solo-license").mkdir()
    (gate.project / ".solo-license" / "policy.toml").write_text(
        "[budget]\nsession_usd = 3\nday_usd = 20\nwarn_at = 0.9\n", encoding="utf-8")
    rules = policy.effective(gate.conn, "shop-api", gate.project)
    assert (rules.budget.session_usd, rules.budget.day_usd, rules.budget.warn_at) == (1.0, 5.0, 0.8)
    assert rules.to_json()["budget"] == {"session_usd": 1.0, "day_usd": 5.0, "warn_at": 0.8}


def test_a_broken_budget_in_the_team_file_freezes(gate):
    (gate.project / ".solo-license").mkdir()
    (gate.project / ".solo-license" / "policy.toml").write_text("[budget]\nsession_usd = -1\n", encoding="utf-8")
    assert policy.effective(gate.conn, "shop-api", gate.project).freeze is True


def test_saving_other_machine_rules_keeps_the_caps(gate):
    policy.save_local(gate.conn, "*", {"deny": {"commands": ["terraform destroy"]}})
    assert policy.local(gate.conn, "*").budget.session_usd == 1.0


def test_policies_without_a_budget_keep_their_digest():
    assert "budget" not in policy.Policy().to_json()


def test_schema_is_idempotent(harness):
    apply_schema(harness.conn)
    apply_schema(harness.conn)
    tables = {r["name"] for r in harness.conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert {"agent_spend", "agent_spend_days", "agent_budget_marks"} <= tables
