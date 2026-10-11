"""The coding gate: earn per action class, lose it on a failure, never pass a forbidden action."""

from __future__ import annotations

import subprocess

import pytest

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


def _bash(gate, command):
    return _event(gate, tool_name="Bash", tool_input={"command": command})


def _approve_and_run(gate, command):
    """The person approves the prompt and the command succeeds."""
    answer = gate.permission(_bash(gate, command))
    gate.tool_result(_bash(gate, command), failed=False)
    return answer


def _license(gate, key):
    return agent_repo.get_license(gate.conn, "shop-api", key)


def test_a_new_repo_starts_at_zero_trust(gate):
    gate.user_prompt(_event(gate, prompt="fix the failing test"))
    answer = gate.permission(_bash(gate, "npm test"))
    assert "hookSpecificOutput" not in answer  # no decision: Claude Code asks the person
    assert "L0" in answer["systemMessage"]


def test_approvals_earn_level_one_then_the_command_runs_alone(gate):
    gate.user_prompt(_event(gate, prompt="fix the failing test"))
    for _ in range(3):
        _approve_and_run(gate, "npm test")
    assert _license(gate, "test-run")["level"] == 1

    answer = gate.permission(_bash(gate, "npm test -- --watch=false"))
    assert answer["hookSpecificOutput"]["decision"]["behavior"] == "allow"

    # The commit is in the license ledger.
    log = subprocess.run(["git", "log", "--format=%s"], cwd=gate.ledger._repo_root,
                         capture_output=True, text=True, check=True).stdout
    assert "license(test-run@shop-api): promote L0 -> L1" in log


def test_level_one_covers_only_the_approved_command_family(gate):
    gate.user_prompt(_event(gate, prompt="x"))
    for _ in range(3):
        _approve_and_run(gate, "npm test")
    assert "hookSpecificOutput" not in gate.permission(_bash(gate, "pytest"))


def test_a_failed_change_demotes_its_class_and_forgets_approvals(gate):
    gate.user_prompt(_event(gate, prompt="add lodash"))
    agent_repo.get_license(gate.conn, "shop-api", "install-dep")
    agent_repo.set_level(gate.conn, "shop-api", "install-dep", 2)

    allowed = gate.permission(_bash(gate, "npm install lodash"))
    assert allowed["hookSpecificOutput"]["decision"]["behavior"] == "allow"
    gate.tool_result(_bash(gate, "npm install lodash") | {"error": "Exit code 1\nERESOLVE"}, failed=True)

    lic = _license(gate, "install-dep")
    assert lic["level"] == 0 and lic["demoted_from"] == 2 and lic["failures"] == 1
    assert "hookSpecificOutput" not in gate.permission(_bash(gate, "npm install lodash"))


def test_a_failing_test_run_is_not_held_against_the_agent(gate):
    gate.user_prompt(_event(gate, prompt="x"))
    gate.permission(_bash(gate, "npm test"))
    gate.tool_result(_bash(gate, "npm test") | {"error": "Exit code 1"}, failed=True)
    lic = _license(gate, "test-run")
    assert lic["successes"] == 1 and lic["failures"] == 0


def test_forbidden_actions_are_denied_even_at_full_trust(gate):
    gate.user_prompt(_event(gate, prompt="ship it"))
    agent_repo.get_license(gate.conn, "shop-api", "git-remote")
    agent_repo.set_level(gate.conn, "shop-api", "git-remote", 1)
    answer = gate.permission(_bash(gate, "git push --force origin main"))
    decision = answer["hookSpecificOutput"]["decision"]
    assert decision["behavior"] == "deny" and "force-pushes" in decision["message"]
    assert _license(gate, "git-remote")["level"] == 0


def test_classes_that_never_auto_run_always_ask(gate):
    gate.user_prompt(_event(gate, prompt="deploy"))
    agent_repo.get_license(gate.conn, "shop-api", "deploy")
    agent_repo.set_level(gate.conn, "shop-api", "deploy", 2)
    assert "hookSpecificOutput" not in gate.permission(_bash(gate, "vercel --prod"))


def test_changes_become_evidence_only_when_the_turn_is_verified(gate):
    gate.user_prompt(_event(gate, prompt="commit the fix"))
    gate.permission(_bash(gate, "git commit -m fix"))
    gate.tool_result(_bash(gate, "git commit -m fix"), failed=False)
    assert _license(gate, "git-local")["successes"] == 0

    assert gate.stop(_event(gate)) == {}
    assert _license(gate, "git-local")["successes"] == 1


def test_a_failed_turn_check_blocks_once_then_closes(gate):
    gate.verifier = lambda g, turn, decisions: (False, "tests fail after the change.", {"tests": "failed"})
    gate.user_prompt(_event(gate, prompt="commit"))
    gate.permission(_bash(gate, "git commit -m x"))
    gate.tool_result(_bash(gate, "git commit -m x"), failed=False)

    blocked = gate.stop(_event(gate))
    assert blocked["decision"] == "block" and "tests fail" in blocked["reason"]
    assert gate.stop(_event(gate, stop_hook_active=True)) == {}
    turn = agent_repo.current_turn(gate.conn, "s1")
    assert turn["status"] == "failed"


def test_hook_endpoint_round_trip(gate, harness, tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from sololicense.api import app as app_module
    from sololicense.db.database import init_db

    # The API serves from worker threads.
    conn = init_db(tmp_path / "api.db", check_same_thread=False)
    threaded = CodingGate(conn, harness.tracer, GitLedger(repo_root=harness.repo), jev_client=JevClient(), checkpoint_lookup=lambda cwd, session: None)

    class Ctx:
        coding_gate = threaded
        conn = threaded.conn

    monkeypatch.setattr(app_module, "get_context", lambda: Ctx)
    client = TestClient(app_module.app)
    assert client.post("/api/hooks/user-prompt", json=_event(gate, prompt="hi")).json() == {}
    answer = client.post("/api/hooks/permission", json=_bash(gate, "ls")).json()
    assert "systemMessage" in answer
    assert client.post("/api/hooks/nope", json={}).status_code == 404


def test_install_merges_with_existing_hooks_and_is_idempotent(tmp_path):
    import json

    from sololicense.coding.install import install

    settings = tmp_path / ".claude" / "settings.local.json"
    settings.parent.mkdir()
    settings.write_text(json.dumps({"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "entire x"}]}]}}))
    install(tmp_path)
    install(tmp_path, "http://localhost:9000")
    hooks = json.loads(settings.read_text())["hooks"]
    assert len(hooks["Stop"]) == 2 and hooks["Stop"][0]["hooks"][0]["command"] == "entire x"
    assert hooks["PermissionRequest"][0]["hooks"][0]["url"] == "http://localhost:9000/api/hooks/permission"


def test_coding_dashboard_lists_licenses_with_progress(gate, harness, tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from sololicense.api import app as app_module
    from sololicense.db.database import init_db

    conn = init_db(tmp_path / "dash.db", check_same_thread=False)
    threaded = CodingGate(conn, harness.tracer, GitLedger(repo_root=harness.repo), jev_client=JevClient(), checkpoint_lookup=lambda cwd, session: None)

    class Ctx:
        coding_gate = threaded

    Ctx.conn = conn
    monkeypatch.setattr(app_module, "get_context", lambda: Ctx)
    client = TestClient(app_module.app)
    client.post("/api/hooks/permission", json=_bash(gate, "npm test"))
    body = client.get("/api/coding?repo=shop-api").json()
    row = next(l for l in body["licenses"] if l["action_class"] == "test-run")
    assert row["level"] == 0 and row["runs_needed"] >= 3
    assert body["counts"]["ask"] == 1


def test_a_person_resumes_a_paused_class_within_its_ceiling(gate):
    gate.user_prompt(_event(gate, prompt="x"))
    agent_repo.get_license(gate.conn, "shop-api", "install-dep")
    agent_repo.set_level(gate.conn, "shop-api", "install-dep", 2)
    gate.permission(_bash(gate, "npm install left-pad"))
    gate.tool_result(_bash(gate, "npm install left-pad") | {"error": "Exit code 1"}, failed=True)
    assert _license(gate, "install-dep")["level"] == 0

    assert gate.restore("shop-api", "install-dep", 2, actor_id="human:jayati", reason="flaky registry") == 2
    assert gate.restore("shop-api", "git-remote", 2, actor_id="human:jayati", reason="x") == 1  # capped
    event = gate.conn.execute("SELECT * FROM agent_events ORDER BY id DESC LIMIT 1").fetchone()
    assert event["kind"] == "restore" and event["actor_id"] == "human:jayati"


def test_every_license_change_is_an_agent_event_with_its_commit(gate):
    gate.user_prompt(_event(gate, prompt="x"))
    for _ in range(3):
        _approve_and_run(gate, "npm test")
    event = gate.conn.execute("SELECT * FROM agent_events ORDER BY id DESC LIMIT 1").fetchone()
    assert (event["repo"], event["principal"], event["action_class"], event["kind"]) == \
        ("shop-api", "main", "test-run", "promote")
    assert (event["from_level"], event["to_level"]) == (0, 1)
    assert event["actor_id"] == "system:coding-gate" and event["git_sha"]
    assert gate.conn.execute(
        "SELECT COUNT(*) FROM license_events WHERE task_class LIKE '%@%'").fetchone()[0] == 0


def test_a_tool_that_ran_after_the_prompt_is_recorded_as_the_persons_approval(gate):
    gate.user_prompt(_event(gate, prompt="x"))
    _approve_and_run(gate, "npm test")
    row = gate.conn.execute("SELECT decided_by, outcome FROM agent_decisions ORDER BY id DESC LIMIT 1").fetchone()
    assert row["decided_by"] == "person" and row["outcome"] == "verified"



def _cursor_shell(gate, command):
    return {"session_id": "cur", "cwd": str(gate.project), "tool_name": "Bash",
            "tool_input": {"command": command}, "_agent": "cursor", "_prompt_only": False}


def test_actions_the_agents_own_settings_let_through_earn_nothing(gate):
    """Trail #26 finding: an agent whose hook fires on every call must not
    unlock L1 just because its own settings ran the command."""
    gate.user_prompt({"session_id": "cur", "cwd": str(gate.project), "prompt": "x", "_agent": "cursor"})
    for _ in range(6):
        gate.permission(_cursor_shell(gate, "npm install left-pad"))
        gate.tool_result(_cursor_shell(gate, "npm install left-pad"), failed=False)
    gate.stop({"session_id": "cur", "cwd": str(gate.project)})
    lic = _license(gate, "install-dep")
    assert lic["level"] == 0 and lic["successes"] == 0
    assert not agent_repo.pattern_approved(gate.conn, "shop-api", "npm install")
    outcomes = {r["outcome"] for r in gate.conn.execute("SELECT outcome FROM agent_decisions WHERE agent = 'cursor'")}
    assert outcomes == {"observed"}


def test_failures_count_whoever_let_the_action_run(gate):
    gate.user_prompt({"session_id": "cur", "cwd": str(gate.project), "prompt": "x", "_agent": "cursor"})
    gate.permission(_cursor_shell(gate, "npm install left-pad"))
    gate.tool_result(_cursor_shell(gate, "npm install left-pad") | {"error": "Exit code 1"}, failed=True)
    assert _license(gate, "install-dep")["failures"] == 1


def test_trust_earned_through_a_person_is_shared_by_every_agent_in_the_repo(gate):
    gate.user_prompt(_event(gate, prompt="x"))
    for _ in range(3):
        _approve_and_run(gate, "npm test")          # Claude Code: a person approved each one
    answer = gate.permission(_cursor_shell(gate, "npm test"))
    assert answer["hookSpecificOutput"]["decision"]["behavior"] == "allow"



def test_the_claude_route_cannot_be_used_to_pose_as_another_agent(gate, harness, tmp_path, monkeypatch):
    """Trail #26 finding: /api/hooks/{event} is Claude Code's alone; a caller
    cannot pick the agent or the prompt-only flag through it."""
    from fastapi.testclient import TestClient

    from sololicense.api import app as app_module
    from sololicense.db.database import init_db

    conn = init_db(tmp_path / "route.db", check_same_thread=False)
    threaded = CodingGate(conn, harness.tracer, GitLedger(repo_root=harness.repo),
                          jev_client=JevClient(), checkpoint_lookup=lambda cwd, session: None)

    class Ctx:
        coding_gate = threaded

    Ctx.conn = conn
    monkeypatch.setattr(app_module, "get_context", lambda: Ctx)
    client = TestClient(app_module.app)
    spoof = {**_bash(gate, "npm test"), "_agent": "cursor", "_prompt_only": False}
    client.post("/api/hooks/permission?agent=cursor", json=spoof)
    row = conn.execute("SELECT agent, decided_by FROM agent_decisions ORDER BY id DESC LIMIT 1").fetchone()
    assert row["agent"] == "claude-code" and row["decided_by"] == "license"

    # The agent route decides prompt-only from the agent itself, not the body.
    client.post("/api/hooks/cursor/beforeShellExecution",
                json={"conversation_id": "k", "command": "npm test", "cwd": str(gate.project), "_prompt_only": True})
    row = conn.execute("SELECT agent, decided_by FROM agent_decisions ORDER BY id DESC LIMIT 1").fetchone()
    assert row["agent"] == "cursor" and row["decided_by"] == "agent-settings"


def test_the_coding_dashboard_lists_license_events(gate, harness, tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from sololicense.api import app as app_module
    from sololicense.db.database import init_db

    conn = init_db(tmp_path / "events.db", check_same_thread=False)
    threaded = CodingGate(conn, harness.tracer, GitLedger(repo_root=harness.repo),
                          jev_client=JevClient(), checkpoint_lookup=lambda cwd, session: None)
    agent_repo.ensure_repo(conn, "shop-api", str(gate.project))
    threaded.restore("shop-api", "test-run", 1, actor_id="human:jayati", reason="reviewed")

    class Ctx:
        coding_gate = threaded

    Ctx.conn = conn
    monkeypatch.setattr(app_module, "get_context", lambda: Ctx)
    events = TestClient(app_module.app).get("/api/coding?repo=shop-api").json()["events"]
    assert [(e["action_class"], e["kind"], e["to_level"]) for e in events] == [("test-run", "restore", 1)]
