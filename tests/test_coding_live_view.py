"""What the dashboard shows of an agent's guidance: remediations it was told
(or will be told) and the loops it was warned about or stopped for."""

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


def _read(gate):
    return _event(gate, tool_name="Read", tool_input={"file_path": "a.py"})


# --- remediations ---------------------------------------------------------------

def test_a_queued_remediation_shows_its_turn_session_and_delivery(gate):
    gate.user_prompt(_event(gate, prompt="refactor"))
    turn = agent_repo.current_turn(gate.conn, "s1")
    gate.flag(turn_id=turn["id"], actor_id="human:jayati", reason="wrong approach")

    [queued] = agent_repo.recent_remediations(gate.conn, repo="shop-api")
    assert (queued["kind"], queued["turn_id"], queued["session_id"], queued["repo"]) == \
        ("flagged", turn["id"], "s1", "shop-api")
    assert "wrong approach" in queued["text"] and queued["created_at"] and queued["delivered_at"] is None

    gate.user_prompt(_event(gate, prompt="carry on"))
    [delivered] = agent_repo.recent_remediations(gate.conn, repo="shop-api")
    assert delivered["delivered_at"]


def test_remediations_are_listed_per_repository(gate):
    gate.user_prompt(_event(gate, prompt="refactor"))
    gate.flag(turn_id=agent_repo.current_turn(gate.conn, "s1")["id"], actor_id="human:j", reason="no")
    assert agent_repo.recent_remediations(gate.conn, repo="another-repo") == []
    assert len(agent_repo.recent_remediations(gate.conn)) == 1


# --- loops ----------------------------------------------------------------------

def test_a_halted_session_and_its_stopped_call_show_while_the_turn_is_open(gate):
    gate.user_prompt(_event(gate, prompt="read it"))
    turn = agent_repo.current_turn(gate.conn, "s1")
    for _ in range(5):
        gate.tool_result(_read(gate), failed=False)
    gate.permission(_bash(gate, "npm test"))

    events = agent_repo.loop_events(gate.conn, repo="shop-api")
    halt = next(e for e in events if e["kind"] == "halt")
    assert (halt["severity"], halt["session_id"], halt["turn_id"], halt["repo"]) == ("stop", "s1", turn["id"], "shop-api")
    assert "5th time" in halt["reason"]
    stop = next(e for e in events if e["kind"] == "loop-stop")
    assert (stop["severity"], stop["turn_id"], stop["command"]) == ("stop", turn["id"], "npm test")
    assert agent_repo.loop_events(gate.conn, repo="another-repo") == []


def test_loop_warnings_show_once_the_turn_is_recorded_and_the_halt_is_gone(gate):
    gate.user_prompt(_event(gate, prompt="test it"))
    turn = agent_repo.current_turn(gate.conn, "s1")
    for _ in range(3):
        gate.permission(_bash(gate, "npm test"))
        gate.tool_result(_bash(gate, "npm test"), failed=False)
    gate.stop(_event(gate))

    [warning] = agent_repo.loop_events(gate.conn, repo="shop-api")
    assert (warning["kind"], warning["severity"], warning["turn_id"], warning["session_id"]) == \
        ("repeat", "warning", turn["id"], "s1")
    assert "3 times" in warning["reason"] and warning["created_at"]


def test_a_call_stopped_at_the_prompt_is_listed_once(gate):
    gate.user_prompt(_event(gate, prompt="install"))
    for _ in range(4):
        gate.permission(_bash(gate, "pip install -e ."))
        gate.tool_result(_bash(gate, "pip install -e .") | {"error": "Exit code 1\nERROR: no setup.py"}, failed=True)
    gate.permission(_bash(gate, "pip install -e ."))
    gate.stop(_event(gate))

    kinds = [e["kind"] for e in agent_repo.loop_events(gate.conn, repo="shop-api")]
    assert kinds.count("loop-stop") == 1
    assert kinds.count("same-failure") == 2


# --- the dashboard payload ------------------------------------------------------

def test_the_coding_payload_carries_remediations_and_loops(gate, harness, tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from sololicense.api import app as app_module
    from sololicense.db.database import init_db

    conn = init_db(tmp_path / "live.db", check_same_thread=False)
    threaded = CodingGate(conn, harness.tracer, GitLedger(repo_root=harness.repo),
                          jev_client=JevClient(), checkpoint_lookup=lambda cwd, session: None)

    class Ctx:
        coding_gate = threaded

    Ctx.conn = conn
    monkeypatch.setattr(app_module, "get_context", lambda: Ctx)
    client = TestClient(app_module.app)
    client.post("/api/hooks/user-prompt", json=_event(gate, prompt="read it"))
    for _ in range(5):
        client.post("/api/hooks/post-tool", json=_read(gate))
    turn_id = agent_repo.current_turn(conn, "s1")["id"]
    threaded.flag(turn_id=turn_id, actor_id="human:jayati", reason="looped")

    payload = client.get("/api/coding", params={"repo": "shop-api"}).json()
    [remedy] = payload["remediations"]
    assert remedy["kind"] == "flagged" and remedy["turn_id"] == turn_id and remedy["delivered_at"] is None
    assert any(e["kind"] == "halt" and e["turn_id"] == turn_id for e in payload["loops"])
    other = client.get("/api/coding", params={"repo": "another-repo"}).json()
    assert other["remediations"] == [] and other["loops"] == []
