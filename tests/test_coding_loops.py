"""Loop and stuck detection: guidance at 3 repeats, a halt at 5, never a demotion."""

from __future__ import annotations

import subprocess

import pytest

from sololicense.coding import loops
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
    return {"session_id": "s1", "cwd": str(gate.project), **fields}


def _bash(gate, command, **extra):
    return _event(gate, tool_name="Bash", tool_input={"command": command, **extra})


def _edit(gate, path="app.py", old="a", new="b"):
    return _event(gate, tool_name="Edit", tool_input={"file_path": path, "old_string": old, "new_string": new})


def _notebook(gate, path="nb.ipynb", cell="c1", source="x = 1"):
    return _event(gate, tool_name="NotebookEdit", tool_input={
        "notebook_path": path, "cell_id": cell, "new_source": source, "cell_type": "code", "edit_mode": "replace"})


def _context(answer):
    return (answer.get("hookSpecificOutput") or {}).get("additionalContext", "")


# --- fingerprints ---------------------------------------------------------------

def test_fingerprints_ignore_spacing_descriptions_and_volatile_values():
    a = loops.fingerprint("Bash", {"command": "curl  http://x/api?ts=2026-10-12T02:30:01Z", "description": "one"})
    b = loops.fingerprint("Bash", {"command": "curl http://x/api?ts=2026-10-12T02:31:59Z", "description": "two"})
    assert a == b
    assert loops.fingerprint("Bash", {"command": "rm build/0123456789abcdef0123"}) == \
        loops.fingerprint("Bash", {"command": "rm build/fedcba9876543210fedc"})
    assert loops.fingerprint("Bash", {"command": "npm test"}) != loops.fingerprint("Bash", {"command": "npm run lint"})
    assert loops.fingerprint("Edit", {"file_path": "a.py", "old_string": "x", "new_string": "y"}) != \
        loops.fingerprint("Edit", {"file_path": "a.py", "old_string": "x", "new_string": "z"})


def test_notebook_edits_are_fingerprinted_by_notebook_cell_and_source():
    base = {"notebook_path": "a.ipynb", "cell_id": "c1", "new_source": "x = 1", "cell_type": "code",
            "edit_mode": "replace"}
    fp = loops.fingerprint("NotebookEdit", base)
    assert fp == loops.fingerprint("NotebookEdit", dict(base))
    for change in ({"notebook_path": "b.ipynb"}, {"cell_id": "c2"}, {"new_source": "x = 2"},
                   {"cell_type": "markdown"}, {"edit_mode": "insert"}):
        assert loops.fingerprint("NotebookEdit", base | change) != fp


def test_the_error_head_skips_the_exit_code_line():
    assert loops.error_head("Exit code 1\n\nError: Cannot find module 'express'\n  at x") == \
        "Error: Cannot find module 'express'"
    assert loops.error_head("Exit code 2") == "Exit code 2"


# --- the gate -------------------------------------------------------------------

def test_a_session_that_loops_is_stopped_by_the_fifth_repeat(gate):
    """Fixture session: the agent keeps running the same failing install."""
    gate.user_prompt(_event(gate, prompt="get the build green"))
    answers = []
    for _ in range(4):
        gate.permission(_bash(gate, "pip install -e ."))
        answers.append(gate.tool_result(_bash(gate, "pip install -e .") | {"error": "Exit code 1\nERROR: no setup.py"},
                                        failed=True))
    assert "keeps failing" not in _context(answers[1])
    assert "keeps failing for the same reason: ERROR: no setup.py" in _context(answers[2])
    assert "Stop retrying it" in _context(answers[2])

    fifth = gate.permission(_bash(gate, "pip install -e ."))
    decision = fifth["hookSpecificOutput"]["decision"]
    assert decision["behavior"] == "deny" and decision["interrupt"] is True
    assert "5th time" in decision["message"]
    row = gate.conn.execute("SELECT decided_by FROM agent_decisions ORDER BY id DESC LIMIT 1").fetchone()
    assert row["decided_by"] == "loop-guard"


def test_three_identical_calls_get_guidance_but_no_demotion(gate):
    gate.user_prompt(_event(gate, prompt="x"))
    agent_repo.get_license(gate.conn, "shop-api", "test-run")
    agent_repo.set_level(gate.conn, "shop-api", "test-run", 2)
    answers = []
    for _ in range(3):
        gate.permission(_bash(gate, "npm test"))
        answers.append(gate.tool_result(_bash(gate, "npm test"), failed=False))
    assert answers[1] == {}
    assert answers[2]["hookSpecificOutput"]["hookEventName"] == "PostToolUse"
    assert "3 times" in _context(answers[2])
    assert agent_repo.get_license(gate.conn, "shop-api", "test-run")["level"] == 2
    assert not gate.conn.execute("SELECT 1 FROM agent_events WHERE kind = 'demote'").fetchone()


def test_an_edit_in_between_means_it_is_not_a_loop(gate):
    gate.user_prompt(_event(gate, prompt="x"))
    for i in range(6):
        answer = gate.tool_result(_bash(gate, "npm test"), failed=False)
        assert answer == {}
        gate.tool_result(_edit(gate, path=f"f{i}.py"), failed=False)


def test_calls_claude_code_never_asks_about_are_halted_after_the_fifth_run(gate):
    gate.user_prompt(_event(gate, prompt="x"))
    answers = [gate.tool_result(_event(gate, tool_name="Read", tool_input={"file_path": "a.py"}), failed=False)
               for _ in range(5)]
    assert "continue" not in answers[3]
    assert answers[4]["continue"] is False and "5th time" in answers[4]["stopReason"]


def test_permission_and_post_tool_count_a_call_once(gate):
    gate.user_prompt(_event(gate, prompt="x"))
    for _ in range(2):
        gate.permission(_bash(gate, "make"))
        gate.tool_result(_bash(gate, "make"), failed=False)
    row = gate.conn.execute("SELECT count FROM agent_fingerprints WHERE fingerprint NOT LIKE 'edit:%'").fetchone()
    assert row["count"] == 2


def _fingerprints(conn, session_id):
    return {r["fingerprint"] for r in conn.execute(
        "SELECT fingerprint FROM agent_fingerprints WHERE session_id = ?", (session_id,))}


def test_an_edit_clears_edit_tool_fingerprints_but_keeps_the_turn_bookkeeping(gate):
    conn = gate.conn
    bash = loops.fingerprint("Bash", {"command": "npm test"})
    edit = loops.fingerprint("Edit", {"file_path": "a.py", "old_string": "x", "new_string": "y"})
    loops.record_edit(conn, "s9", 1, "a.py")
    loops.record(conn, "s9", bash, failed=False)
    loops.record(conn, "s9", edit, failed=False)
    loops.record_edit(conn, "s9", 1, "b.py")
    assert _fingerprints(conn, "s9") == {"edit:1:a.py", "edit:1:b.py"}


def test_a_new_turn_drops_the_edit_bookkeeping_of_earlier_turns(gate):
    conn = gate.conn
    loops.record_edit(conn, "s9", 1, "a.py")
    loops.record_edit(conn, "s9", 1, "b.py")
    loops.record_edit(conn, "s8", 1, "a.py")
    loops.record_edit(conn, "s9", 12, "a.py")
    assert _fingerprints(conn, "s9") == {"edit:12:a.py"}
    assert _fingerprints(conn, "s8") == {"edit:1:a.py"}
    loops.record_edit(conn, "s9", 1, "c.py")
    assert _fingerprints(conn, "s9") == {"edit:1:c.py"}


def test_the_window_caps_edit_tool_fingerprints_too(gate):
    conn = gate.conn
    loops.record_edit(conn, "s9", 1, "a.py")
    for i in range(loops.WINDOW + 5):
        loops.record(conn, "s9", loops.fingerprint("Edit", {"file_path": f"f{i}.py"}), failed=False)
    remembered = _fingerprints(conn, "s9")
    assert "edit:1:a.py" in remembered
    assert len(remembered - {"edit:1:a.py"}) == loops.WINDOW


def test_a_halt_outlives_the_window_and_an_edit(gate):
    conn = gate.conn
    loops.halt(conn, "s9", "stuck")
    for i in range(loops.WINDOW + 5):
        loops.record(conn, "s9", loops.fingerprint("Bash", {"command": f"echo {i}"}), failed=False)
    loops.record_edit(conn, "s9", 1, "a.py")
    assert _fingerprints(conn, "s9") == {"halt", "edit:1:a.py"}
    assert loops.halted(conn, "s9") == "stuck"


def test_editing_the_same_file_again_and_again_sends_the_turn_back_once(gate):
    gate.user_prompt(_event(gate, prompt="fix app.py"))
    for i in range(4):
        gate.tool_result(_edit(gate, old=str(i), new=str(i + 1)), failed=False)
    blocked = gate.stop(_event(gate))
    assert blocked["decision"] == "block" and "app.py" in blocked["reason"] and "4 times" in blocked["reason"]
    assert gate.stop(_event(gate, stop_hook_active=True)) == {}
    assert not gate.conn.execute("SELECT 1 FROM agent_events WHERE kind = 'demote'").fetchone()


def test_distinct_notebook_edits_are_not_a_loop(gate):
    gate.user_prompt(_event(gate, prompt="x"))
    answers = [gate.tool_result(_notebook(gate, path=f"nb{i}.ipynb", cell=f"c{i}", source=f"x = {i}"),
                                failed=False) for i in range(5)]
    assert answers == [{}] * 5


def test_editing_the_same_notebook_again_and_again_sends_the_turn_back_once(gate):
    gate.user_prompt(_event(gate, prompt="fix nb.ipynb"))
    for i in range(4):
        gate.tool_result(_notebook(gate, source=f"x = {i}"), failed=False)
    blocked = gate.stop(_event(gate))
    assert blocked["decision"] == "block" and "nb.ipynb" in blocked["reason"] and "4 times" in blocked["reason"]


def test_a_loop_stop_holds_for_every_call_until_the_next_prompt(gate):
    gate.user_prompt(_event(gate, prompt="x"))
    for _ in range(5):
        gate.tool_result(_event(gate, tool_name="Read", tool_input={"file_path": "a.py"}), failed=False)
    gate.tool_result(_edit(gate), failed=False)
    denied = gate.permission(_bash(gate, "npm test"))["hookSpecificOutput"]["decision"]
    assert denied["behavior"] == "deny" and denied["interrupt"] is True and "5th time" in denied["message"]

    gate.user_prompt(_event(gate, prompt="try something else"))
    assert "hookSpecificOutput" not in gate.permission(_bash(gate, "npm test"))


def test_the_end_of_a_turn_clears_a_loop_stop(gate):
    gate.user_prompt(_event(gate, prompt="x"))
    for _ in range(5):
        gate.tool_result(_event(gate, tool_name="Read", tool_input={"file_path": "a.py"}), failed=False)
    gate.stop(_event(gate))
    assert loops.halted(gate.conn, "s1") == ""


@pytest.fixture
def client(harness, tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from sololicense.api import app as app_module
    from sololicense.db.database import init_db

    conn = init_db(tmp_path / "loops.db", check_same_thread=False)
    threaded = CodingGate(conn, harness.tracer, GitLedger(repo_root=harness.repo),
                          jev_client=JevClient(), checkpoint_lookup=lambda cwd, session: None)

    class Ctx:
        coding_gate = threaded

    Ctx.conn = conn
    monkeypatch.setattr(app_module, "get_context", lambda: Ctx)
    return TestClient(app_module.app)


def test_cursor_is_stopped_at_its_next_pre_tool_hook(gate, client):
    shell = {"conversation_id": "cu", "cwd": str(gate.project), "command": "ls"}
    answers = [client.post("/api/hooks/cursor/afterShellExecution", json=shell).json() for _ in range(5)]
    assert answers[4] == {}
    other = client.post("/api/hooks/cursor/beforeShellExecution", json=shell | {"command": "git status"}).json()
    assert other["permission"] == "deny" and "5th time" in other["agent_message"]

    client.post("/api/hooks/cursor/beforeSubmitPrompt", json={"conversation_id": "cu", "cwd": str(gate.project),
                                                               "prompt": "go on"})
    again = client.post("/api/hooks/cursor/beforeShellExecution", json=shell | {"command": "git status"}).json()
    assert again.get("permission") != "deny"


def test_copilot_is_stopped_at_its_next_pre_tool_hook(gate, client):
    call = {"sessionId": "cp", "cwd": str(gate.project), "toolName": "view", "toolArgs": {"path": "a.py"}}
    answers = [client.post("/api/hooks/copilot/postToolUse", json=call).json() for _ in range(5)]
    assert answers[4] == {}
    other = client.post("/api/hooks/copilot/preToolUse", json=call | {"toolName": "bash",
                                                                      "toolArgs": {"command": "ls"}}).json()
    assert other["permissionDecision"] == "deny" and "5th time" in other["permissionDecisionReason"]


def test_gemini_and_cline_are_stopped_by_the_post_tool_hook_itself(gate, client):
    gemini = {"session_id": "ge", "cwd": str(gate.project), "tool_name": "read_file",
              "tool_input": {"absolute_path": "a.py"}}
    fifth = [client.post("/api/hooks/gemini/AfterTool", json=gemini).json() for _ in range(5)][4]
    assert fifth["continue"] is False and "5th time" in fifth["stopReason"]

    cline = {"taskId": "cl", "cwd": str(gate.project),
             "postToolUse": {"toolName": "read_file", "parameters": {"path": "a.py"}, "success": True}}
    fifth = [client.post("/api/hooks/cline/PostToolUse", json=cline).json() for _ in range(5)][4]
    assert fifth["cancel"] is True and "5th time" in fifth["errorMessage"]


def test_loop_guidance_reaches_codex_and_is_a_no_op_for_cursor(gate, client):
    call = {"session_id": "cx", "cwd": str(gate.project), "tool_name": "Bash", "tool_input": {"command": "ls"}}
    answers = [client.post("/api/hooks/codex/PostToolUse", json=call).json() for _ in range(3)]
    assert "3 times" in answers[2]["hookSpecificOutput"]["additionalContext"]
    shell = {"conversation_id": "cu", "cwd": str(gate.project), "command": "ls"}
    assert [client.post("/api/hooks/cursor/afterShellExecution", json=shell).json() for _ in range(3)][2] == {}


def test_a_new_prompt_starts_the_repeat_count_again(harness):
    from sololicense.coding import loops

    for _ in range(4):
        loops.record(harness.conn, "s-new", "bash:npm test", failed=False)
    assert loops.seen(harness.conn, "s-new", "bash:npm test").count == 4
    loops.halt(harness.conn, "s-new", "stopped")
    loops.new_prompt(harness.conn, "s-new")
    assert loops.seen(harness.conn, "s-new", "bash:npm test").count == 0
    assert loops.halted(harness.conn, "s-new") == ""
