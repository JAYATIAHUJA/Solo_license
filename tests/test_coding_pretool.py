"""Claude Code's PreToolUse: what no permission mode may skip, and nothing else.

PermissionRequest never fires under --dangerously-skip-permissions (or for calls
the settings already allow), so forbidden actions and loop stops are refused one
hook earlier. Everything else gets no decision and is counted where it always was.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from sololicense.coding import loops, policy
from sololicense.coding.gate import CodingGate
from sololicense.coding.jev import JevClient
from sololicense.db.repositories import agent as agent_repo
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
    return gate


def _event(gate, **fields):
    return {"session_id": "s1", "cwd": str(gate.project), "permission_mode": "bypassPermissions", **fields}


def _bash(gate, command):
    return _event(gate, tool_name="Bash", tool_input={"command": command})


def _pre(answer):
    return (answer.get("hookSpecificOutput") or {})


def _decisions(gate):
    return gate.conn.execute("SELECT * FROM agent_decisions ORDER BY id").fetchall()


def _repeat_count(gate, tool, tool_input):
    return loops.seen(gate.conn, "s1", loops.fingerprint(tool, tool_input)).count


# --- denied before the tool runs, in any permission mode ---------------------------

def test_bypass_mode_force_push_is_denied_at_pre_tool_use(gate):
    """No PermissionRequest ever fires: PreToolUse is the only chance to refuse."""
    gate.user_prompt(_event(gate, prompt="ship it"))
    agent_repo.get_license(gate.conn, "shop-api", "git-remote")
    agent_repo.set_level(gate.conn, "shop-api", "git-remote", 1)

    answer = gate.pre_tool(_bash(gate, "git push --force origin main"))

    out = _pre(answer)
    assert out["hookEventName"] == "PreToolUse" and out["permissionDecision"] == "deny"
    assert "force-pushes" in out["permissionDecisionReason"]
    [row] = _decisions(gate)
    assert (row["decision"], row["decided_by"], row["outcome"]) == ("deny", "hard-deny", "denied")
    assert agent_repo.get_license(gate.conn, "shop-api", "git-remote")["level"] == 0


def test_a_policy_forbidden_command_is_denied_at_pre_tool_use(gate):
    (gate.project / ".solo-license").mkdir()
    (gate.project / ".solo-license" / "policy.toml").write_text('[deny]\ncommands = ["terraform destroy"]\n')
    gate.user_prompt(_event(gate, prompt="clean up"))
    out = _pre(gate.pre_tool(_bash(gate, "terraform destroy -auto-approve")))
    assert out["permissionDecision"] == "deny" and "terraform destroy" in out["permissionDecisionReason"]
    assert [r["decided_by"] for r in _decisions(gate)] == ["policy"]


def test_a_policy_forbidden_file_edit_is_denied_at_pre_tool_use(gate):
    gate.user_prompt(_event(gate, prompt="x"))
    policy.save_local(gate.conn, "shop-api", {"deny": {"paths": [".env"]}})
    edit = _event(gate, tool_name="Write", tool_input={"file_path": str(gate.project / ".env"), "content": "K=1"})
    assert _pre(gate.pre_tool(edit))["permissionDecision"] == "deny"


def test_a_loop_halt_is_denied_at_pre_tool_use_and_stops_the_agent(gate):
    gate.user_prompt(_event(gate, prompt="x"))
    for _ in range(5):  # bypass mode: only PostToolUse saw these
        gate.tool_result(_event(gate, tool_name="Read", tool_input={"file_path": "a.py"}), failed=False)
    answer = gate.pre_tool(_bash(gate, "npm test"))
    out = _pre(answer)
    assert out["permissionDecision"] == "deny" and "5th time" in out["permissionDecisionReason"]
    assert answer["continue"] is False and "5th time" in answer["stopReason"]
    assert [r["decided_by"] for r in _decisions(gate)] == ["loop-guard"]

    gate.user_prompt(_event(gate, prompt="try something else"))
    assert gate.pre_tool(_bash(gate, "npm test")) == {}


def test_the_fifth_identical_call_is_refused_before_it_runs(gate):
    gate.user_prompt(_event(gate, prompt="get the build green"))
    for _ in range(4):
        assert gate.pre_tool(_bash(gate, "pip install -e .")) == {}
        gate.tool_result(_bash(gate, "pip install -e .") | {"error": "Exit code 1\nno setup.py"}, failed=True)
    out = _pre(gate.pre_tool(_bash(gate, "pip install -e .")))
    assert out["permissionDecision"] == "deny" and "5th time" in out["permissionDecisionReason"]
    assert _repeat_count(gate, "Bash", {"command": "pip install -e ."}) == 4  # the refused call never ran


def test_repeated_forbidden_attempts_interrupt_the_agent_on_the_third(gate):
    gate.user_prompt(_event(gate, prompt="ship"))
    answers = [gate.pre_tool(_bash(gate, f"git push -f origin main # {i}")) for i in range(3)]
    assert all(_pre(a)["permissionDecision"] == "deny" for a in answers)
    assert "continue" not in answers[1]
    assert answers[2]["continue"] is False
    assert len(_decisions(gate)) == 3


# --- everything else: no decision, nothing recorded -------------------------------

def test_an_ordinary_call_passes_through_with_no_decision(gate):
    gate.user_prompt(_event(gate, prompt="x"))
    turns_before = gate.conn.execute("SELECT COUNT(*) FROM agent_turns").fetchone()[0]
    for call in (_bash(gate, "npm test"), _bash(gate, "vercel --prod"),
                 _event(gate, tool_name="Edit", tool_input={"file_path": "app.py", "old_string": "a",
                                                            "new_string": "b"})):
        assert gate.pre_tool(call) == {}
    assert _decisions(gate) == []
    assert gate.conn.execute("SELECT COUNT(*) FROM agent_turns").fetchone()[0] == turns_before
    assert gate.conn.execute("SELECT COUNT(*) FROM agent_fingerprints").fetchone()[0] == 0


def test_a_pass_through_opens_no_turn_on_its_own(gate):
    assert gate.pre_tool(_bash(gate, "npm test")) == {}
    assert agent_repo.current_turn(gate.conn, "s1") is None


def test_pre_tool_then_permission_records_one_decision_and_one_run(gate):
    """Default mode: both hooks fire for a call that prompts. It counts once."""
    gate.user_prompt(_event(gate, prompt="x", permission_mode="default"))
    for _ in range(2):
        call = _bash(gate, "make")
        assert gate.pre_tool(call) == {}
        gate.permission(call)
        gate.tool_result(call, failed=False)
    assert len(_decisions(gate)) == 2
    assert _repeat_count(gate, "Bash", {"command": "make"}) == 2


def test_a_call_denied_at_pre_tool_is_never_counted_as_run(gate):
    gate.user_prompt(_event(gate, prompt="x"))
    gate.pre_tool(_bash(gate, "git push --force origin main"))
    assert _repeat_count(gate, "Bash", {"command": "git push --force origin main"}) == 0
    assert agent_repo.pending_decision(gate.conn, "s1", "Bash", "git push --force origin main") is None


def test_a_freeze_makes_changes_ask_even_in_bypass_mode_and_leaves_reads_alone(gate):
    gate.user_prompt(_event(gate, prompt="x"))
    policy.save_local(gate.conn, policy.ALL_REPOS, {"freeze": {"enabled": True}})
    out = _pre(gate.pre_tool(_bash(gate, "npm test")))
    assert out["permissionDecision"] == "ask" and "Frozen" in out["permissionDecisionReason"]
    assert gate.pre_tool(_event(gate, tool_name="Read", tool_input={"file_path": "app.py"})) == {}
    assert _decisions(gate) == []  # the PermissionRequest that follows records it


# --- the hook routes and the installers ---------------------------------------------

@pytest.fixture
def client(harness, tmp_path, monkeypatch, gate):
    from fastapi.testclient import TestClient

    from sololicense.api import app as app_module
    from sololicense.db.database import init_db

    conn = init_db(tmp_path / "pretool.db", check_same_thread=False)
    threaded = CodingGate(conn, harness.tracer, GitLedger(repo_root=harness.repo),
                          jev_client=JevClient(), checkpoint_lookup=lambda cwd, session: None)

    class Ctx:
        coding_gate = threaded

    Ctx.conn = conn
    monkeypatch.setattr(app_module, "get_context", lambda: Ctx)
    return TestClient(app_module.app)


def test_the_claude_code_pre_tool_route(gate, client):
    denied = client.post("/api/hooks/pre-tool", json=_bash(gate, "git push --force origin main")).json()
    assert denied["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert client.post("/api/hooks/pre-tool", json=_bash(gate, "npm test")).json() == {}


def test_the_native_claude_code_pre_tool_route(gate, client):
    payload = _bash(gate, "git push --force origin main") | {"hook_event_name": "PreToolUse"}
    denied = client.post("/api/hooks/claude-code/PreToolUse", json=payload).json()
    assert denied["hookSpecificOutput"] == {
        "hookEventName": "PreToolUse", "permissionDecision": "deny",
        "permissionDecisionReason": denied["hookSpecificOutput"]["permissionDecisionReason"]}
    assert client.post("/api/hooks/claude-code/PreToolUse", json=_bash(gate, "npm test")).json() == {}


def test_install_writes_the_pre_tool_use_hook(tmp_path):
    from sololicense.coding.install import install

    install(tmp_path, "http://localhost:9000")
    hooks = json.loads((tmp_path / ".claude" / "settings.local.json").read_text())["hooks"]
    [entry] = hooks["PreToolUse"]
    assert entry["matcher"] == "*"
    assert entry["hooks"][0]["url"] == "http://localhost:9000/api/hooks/pre-tool"
    install(tmp_path, "http://localhost:9000")
    assert len(json.loads((tmp_path / ".claude" / "settings.local.json").read_text())["hooks"]["PreToolUse"]) == 1


def test_the_plugin_registers_the_pre_tool_use_hook():
    plugin = Path(__file__).resolve().parents[1] / "plugin" / "solo-license" / "hooks" / "hooks.json"
    [entry] = json.loads(plugin.read_text())["hooks"]["PreToolUse"]
    assert entry["matcher"] == "*"
    assert entry["hooks"][0]["url"].endswith("/api/hooks/pre-tool")
