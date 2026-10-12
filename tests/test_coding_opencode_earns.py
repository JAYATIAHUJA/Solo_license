"""OpenCode's hook fires on every call, so on its own it cannot tell a person's
yes from OpenCode's own settings. Its permission.ask hook can: a call OpenCode
asked a person about, which then ran, is that person's yes - and earns trust."""

from __future__ import annotations

import subprocess

import pytest

from sololicense.coding import agents
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
    (project / "a.txt").write_text("a\n")
    subprocess.run(["git", "add", "."], cwd=project, check=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=project, check=True)
    gate = CodingGate(harness.conn, harness.tracer, GitLedger(repo_root=harness.repo),
                      jev_client=JevClient(), checkpoint_lookup=lambda cwd, session: None)
    gate.project = project
    return gate


def _call(gate, native_event, payload):
    event, body = agents.normalize("opencode", native_event, {"sessionID": "oc1", "cwd": str(gate.project),
                                                              **payload})
    body.update(_agent="opencode", _prompt_only=False)
    if event == agents.PERMISSION:
        answer = gate.permission(body)
    elif event == agents.PERSON_ASKED:
        answer = gate.person_asked(body)
    else:
        answer = gate.tool_result(body, failed=event == agents.POST_FAIL)
    return agents.render("opencode", native_event, answer)


def _run_tests(gate, *, asked: bool):
    bash = {"tool_name": "bash", "tool_input": {"command": "npm test"}}
    before = _call(gate, "tool.execute.before", bash)
    if asked:
        _call(gate, "permission.ask", {})
    _call(gate, "tool.execute.after", bash)
    return before


def test_a_call_opencode_ran_on_its_own_settings_is_only_observed(gate):
    _run_tests(gate, asked=False)
    row = gate.conn.execute("SELECT outcome, decided_by FROM agent_decisions").fetchone()
    assert row["outcome"] == "observed" and row["decided_by"] == "agent-settings"


def test_approvals_through_permission_ask_promote_and_then_opencode_runs_it_alone(gate):
    for _ in range(3):
        assert _run_tests(gate, asked=True).body in (None, {})   # not earned yet: OpenCode asks
    rows = gate.conn.execute("SELECT outcome, decided_by FROM agent_decisions ORDER BY id").fetchall()
    assert {r["decided_by"] for r in rows} == {"person"} and {r["outcome"] for r in rows} == {"verified"}
    assert agent_repo.get_license(gate.conn, "shop-api", "test-run")["level"] >= 1

    earned = _run_tests(gate, asked=False)
    assert earned.body["decision"] == "allow"                     # the plugin skips the prompt


def test_permission_ask_without_a_pending_call_changes_nothing(gate):
    _call(gate, "permission.ask", {})
    assert gate.conn.execute("SELECT COUNT(*) AS n FROM agent_decisions").fetchone()["n"] == 0


def test_the_plugin_answers_permission_ask_from_what_was_earned(tmp_path):
    from sololicense.coding.install import install

    path = install(tmp_path, "http://127.0.0.1:8000", "opencode")
    text = path.read_text(encoding="utf-8")
    assert '"permission.ask"' in text and 'output.status = "allow"' in text
    assert 'gate("permission.ask"' in text
