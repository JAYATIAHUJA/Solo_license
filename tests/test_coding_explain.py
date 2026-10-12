"""A turn's whole story in one place: the dashboard's Trace links and
``solo-license explain``."""

from __future__ import annotations

import subprocess

import pytest

from sololicense import cli
from sololicense.coding.gate import CodingGate
from sololicense.coding.jev import JevClient
from sololicense.db.repositories import agent as agent_repo
from sololicense.services.git_ledger import GitLedger


@pytest.fixture
def gate(harness, tmp_path):
    project = tmp_path / "shop-api"
    project.mkdir()
    for args in (["init", "-q"], ["config", "user.name", "T"], ["config", "user.email", "t@e.c"]):
        subprocess.run(["git", *args], cwd=project, check=True)
    (project / "package.json").write_text("{}\n")
    subprocess.run(["git", "add", "."], cwd=project, check=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=project, check=True)
    gate = CodingGate(harness.conn, harness.tracer, GitLedger(repo_root=harness.repo),
                      jev_client=JevClient(), checkpoint_lookup=lambda cwd, session: {"checkpoint_id": "a1b2c3d4e5f6a7b8"})
    gate.project = project
    return gate


def _ev(gate, **fields):
    return {"session_id": "s1", "cwd": str(gate.project), **fields}


def _failed_install(gate):
    gate.user_prompt(_ev(gate, prompt="add left-pad"))
    agent_repo.get_license(gate.conn, "shop-api", "install-dep")
    agent_repo.set_level(gate.conn, "shop-api", "install-dep", 2)
    gate.conn.commit()
    bash = _ev(gate, tool_name="Bash", tool_input={"command": "npm install left-pad"})
    gate.permission(bash)
    gate.tool_result({**bash, "error": "npm ERR! 404 left-pad"}, failed=True)
    gate.stop(_ev(gate))  # the turn ends: its trace is flushed
    return gate.conn.execute("SELECT id FROM agent_turns ORDER BY id DESC LIMIT 1").fetchone()["id"]


class _Ctx:
    config = None


def test_a_turn_story_has_decisions_told_license_changes_and_its_trace(gate):
    from sololicense.api.app import turn_story

    turn_id = _failed_install(gate)
    ctx = _Ctx()
    ctx.conn = gate.conn
    story = turn_story(ctx, turn_id)
    assert story["turn"]["prompt"] == "add left-pad" and story["turn"]["neatlogs_link"] is None
    [decision] = story["decisions"]
    assert decision["command"] == "npm install left-pad" and decision["outcome"] == "failed"
    assert any(e["kind"] == "demote" and e["action_class"] == "install-dep" for e in story["events"])
    names = [s["name"] for s in story["spans"]]
    assert "turn.start" in names and "tool.failed" in names
    assert story["told"] and "left-pad" in story["told"][0]["text"]
    agent_repo.close_turn(gate.conn, turn_id, status="verified", reason="")
    assert story["rewind"]["available"] in (True, False)
    assert turn_story(ctx, turn_id)["rewind"]["available"] is False
    agent_repo.close_turn(gate.conn, turn_id, status="failed", reason="tests failed")
    assert turn_story(ctx, turn_id)["rewind"]["available"] is True
    assert turn_story(ctx, 9999) is None


def test_explain_prints_the_story_and_picks_the_newest_failed_turn(gate):
    from sololicense.api.app import turn_story

    turn_id = _failed_install(gate)
    agent_repo.close_turn(gate.conn, turn_id, status="failed", reason="npm install failed")
    ctx = _Ctx()
    ctx.conn = gate.conn
    text = "\n".join(cli.explain_lines(turn_story(ctx, turn_id)))
    assert f"Turn {turn_id} in shop-api" in text and '"add left-pad"' in text
    assert "deny" in text or "allow" in text
    assert "License: install-dep demote L2 -> L0" in text
    assert "local only; add NEATLOGS_API_KEY" in text and "turn.start ->" in text
    assert "Rewind: Press Rewind" in text

    turns = [{"id": 3, "status": "verified"}, {"id": 2, "status": "failed"}, {"id": 1, "status": "verified"}]
    assert cli.pick_turn(turns)["id"] == 2
    assert cli.pick_turn([{"id": 5, "status": "verified"}])["id"] == 5
    assert cli.pick_turn([]) is None


def test_explain_reports_a_gate_that_is_down(capsys, monkeypatch):
    monkeypatch.setattr(cli, "_get", lambda url, timeout=3.0: None)
    assert cli.main(["explain", "--url", "http://127.0.0.1:9"]) == 1
    assert "not answering" in capsys.readouterr().out


def test_turns_and_decisions_carry_their_neatlogs_link(gate, monkeypatch):
    from dataclasses import replace

    from sololicense.api.app import coding_payload
    from sololicense.config import load_config

    _failed_install(gate)
    config = replace(load_config(), neatlogs_api_key="nl_test", neatlogs_app_url="https://app.neatlogs.com")
    ctx = _Ctx()
    ctx.conn, ctx.config, ctx.coding_gate = gate.conn, config, gate
    body = coding_payload(ctx)
    turn, decision = body["turns"][0], body["decisions"][0]
    assert turn["neatlogs_link"] == f"https://app.neatlogs.com/traces/{turn['trace_id']}"
    assert decision["neatlogs_link"].startswith("https://app.neatlogs.com/traces/")
