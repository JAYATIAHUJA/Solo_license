"""A person flags a decision or a turn: the class drops to L0 and the agent is told."""

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


def _event(gate, **fields):
    return {"session_id": "s1", "cwd": str(gate.project), **fields}


def _bash(gate, command):
    return _event(gate, tool_name="Bash", tool_input={"command": command})


def _license(gate, key):
    return agent_repo.get_license(gate.conn, "shop-api", key)


@pytest.fixture
def gate(harness, tmp_path):
    project = _git_init(tmp_path / "shop-api")
    gate = CodingGate(harness.conn, harness.worker._tracer, GitLedger(repo_root=harness.repo),
                      jev_client=JevClient(), checkpoint_lookup=lambda cwd, session: None)
    gate.project = project
    return gate


def _allowed_install(gate):
    gate.user_prompt(_event(gate, prompt="add left-pad"))
    agent_repo.get_license(gate.conn, "shop-api", "install-dep")
    agent_repo.set_level(gate.conn, "shop-api", "install-dep", 2)
    agent_repo.approve_pattern(gate.conn, "shop-api", "install-dep", "npm install")
    gate.permission(_bash(gate, "npm install left-pad"))
    gate.tool_result(_bash(gate, "npm install left-pad"), failed=False)
    return gate.conn.execute("SELECT * FROM agent_decisions ORDER BY id DESC LIMIT 1").fetchone()


def test_flagging_a_decision_resets_its_class_to_zero_with_a_ledger_commit(gate):
    decision = _allowed_install(gate)
    result = gate.flag(decision_id=decision["id"], actor_id="human:jayati", reason="we do not want left-pad")

    assert result["classes"] == ["install-dep"] and result["session_id"] == "s1"
    lic = _license(gate, "install-dep")
    assert lic["level"] == 0 and lic["demoted_from"] == 2
    assert not agent_repo.pattern_approved(gate.conn, "shop-api", "npm install")
    event = gate.conn.execute("SELECT * FROM agent_events ORDER BY id DESC LIMIT 1").fetchone()
    assert (event["kind"], event["action_class"], event["from_level"], event["to_level"]) == \
        ("flag", "install-dep", 2, 0)
    assert event["actor_id"] == "human:jayati" and event["git_sha"]
    log = subprocess.run(["git", "log", "--format=%s"], cwd=gate.ledger._repo_root,
                         capture_output=True, text=True, check=True).stdout
    assert "flag(install-dep@shop-api): L2 -> L0" in log
    flag = gate.conn.execute("SELECT * FROM agent_flags").fetchone()
    assert flag["decision_id"] == decision["id"] and flag["actor_id"] == "human:jayati"


def test_the_flagged_session_hears_about_it_once_at_its_next_prompt(gate):
    decision = _allowed_install(gate)
    gate.stop(_event(gate))
    gate.flag(decision_id=decision["id"], actor_id="human:jayati", reason="we do not want left-pad")

    context = gate.user_prompt(_event(gate, prompt="carry on"))["hookSpecificOutput"]["additionalContext"]
    assert context.startswith("Solo License: Your last turn was flagged by the user: we do not want left-pad.")
    assert "install-dep is back to asking" in context and "npm install left-pad" in context
    assert gate.user_prompt(_event(gate, prompt="and again")) == {}
    assert gate.conn.execute("SELECT delivered_at FROM agent_flags").fetchone()["delivered_at"]


def test_flagging_a_turn_drops_every_class_that_ran_in_it(gate):
    gate.user_prompt(_event(gate, prompt="commit and install"))
    for key in ("git-local", "install-dep"):
        agent_repo.get_license(gate.conn, "shop-api", key)
        agent_repo.set_level(gate.conn, "shop-api", key, 2)
    for command in ("git commit -m x", "npm install zod"):
        gate.permission(_bash(gate, command))
        gate.tool_result(_bash(gate, command), failed=False)
    gate.permission(_bash(gate, "npm test"))  # asked, never ran: not part of what is flagged
    turn = agent_repo.current_turn(gate.conn, "s1")

    result = gate.flag(turn_id=turn["id"], actor_id="human:jayati", reason="wrong approach")
    assert result["classes"] == ["git-local", "install-dep"]
    assert _license(gate, "git-local")["level"] == 0 and _license(gate, "install-dep")["level"] == 0
    assert _license(gate, "test-run")["level"] == 0
    kinds = [r["kind"] for r in gate.conn.execute("SELECT kind FROM agent_events WHERE kind = 'flag'")]
    assert len(kinds) == 2


def test_a_turn_with_no_gated_actions_still_drops_file_edits(gate):
    gate.user_prompt(_event(gate, prompt="refactor"))
    turn = agent_repo.current_turn(gate.conn, "s1")
    assert gate.flag(turn_id=turn["id"], actor_id="human:j", reason="no")["classes"] == ["file-edit"]


def test_unknown_or_missing_targets_are_refused(gate):
    with pytest.raises(LookupError):
        gate.flag(decision_id=999, actor_id="human:j", reason="x")
    with pytest.raises(LookupError):
        gate.flag(turn_id=999, actor_id="human:j", reason="x")
    with pytest.raises(ValueError):
        gate.flag(actor_id="human:j", reason="x")


def test_flag_api_drops_the_level_and_the_next_prompt_carries_the_message(gate, harness, tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from sololicense.api import app as app_module
    from sololicense.db.database import init_db
    from sololicense.security import Actor, Role

    conn = init_db(tmp_path / "flags.db", check_same_thread=False)
    threaded = CodingGate(conn, harness.worker._tracer, GitLedger(repo_root=harness.repo),
                          jev_client=JevClient(), checkpoint_lookup=lambda cwd, session: None)

    class Ctx:
        coding_gate = threaded

    Ctx.conn = conn
    monkeypatch.setattr(app_module, "get_context", lambda: Ctx)
    app_module.app.dependency_overrides[app_module.current_actor] = \
        lambda: Actor(actor_id="human:jayati", role=Role.APPROVER)
    try:
        client = TestClient(app_module.app)
        client.post("/api/hooks/user-prompt", json=_event(gate, prompt="add left-pad"))
        agent_repo.get_license(conn, "shop-api", "install-dep")
        agent_repo.set_level(conn, "shop-api", "install-dep", 2)
        conn.commit()
        client.post("/api/hooks/permission", json=_bash(gate, "npm install left-pad"))
        client.post("/api/hooks/post-tool", json=_bash(gate, "npm install left-pad"))
        decision_id = conn.execute("SELECT id FROM agent_decisions ORDER BY id DESC LIMIT 1").fetchone()["id"]

        body = client.post("/api/coding/flags", json={"decision_id": decision_id, "reason": "not this package"})
        assert body.status_code == 200
        payload = body.json()
        row = next(l for l in payload["licenses"] if l["action_class"] == "install-dep")
        assert row["level"] == 0
        assert payload["events"][0]["kind"] == "flag" and payload["events"][0]["git_sha"]
        assert payload["flags"][0]["reason"] == "not this package"

        first = client.post("/api/hooks/user-prompt", json=_event(gate, prompt="next")).json()
        assert "Your last turn was flagged by the user: not this package." in \
            first["hookSpecificOutput"]["additionalContext"]
        assert client.post("/api/hooks/user-prompt", json=_event(gate, prompt="again")).json() == {}

        assert client.post("/api/coding/flags", json={"reason": "x"}).status_code == 422
        assert client.post("/api/coding/flags", json={"decision_id": 9999, "reason": "x"}).status_code == 422
        assert client.post("/api/coding/flags", json={"decision_id": decision_id, "reason": ""}).status_code == 422
    finally:
        app_module.app.dependency_overrides.clear()
