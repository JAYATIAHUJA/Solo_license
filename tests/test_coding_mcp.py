"""MCP tools: one license per server, risk per tool, destructive tools keep asking."""

from __future__ import annotations

import subprocess

import pytest

from sololicense.coding import policy
from sololicense.coding.gate import CodingGate
from sololicense.coding.jev import JevClient
from sololicense.db.repositories import agent as agent_repo
from sololicense.services.git_ledger import GitLedger


@pytest.fixture
def gate(harness, tmp_path):
    project = tmp_path / "shop-api"
    project.mkdir()
    for args in (["init", "-q"], ["config", "user.name", "T"], ["config", "user.email", "t@example.com"]):
        subprocess.run(["git", *args], cwd=project, check=True)
    (project / "app.py").write_text("x = 1\n")
    subprocess.run(["git", "add", "."], cwd=project, check=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=project, check=True)
    g = CodingGate(harness.conn, harness.tracer, GitLedger(repo_root=harness.repo),
                   jev_client=JevClient(), checkpoint_lookup=lambda cwd, session: None)
    g.project = project
    g.user_prompt({"session_id": "s", "cwd": str(project), "prompt": "triage the issues"})
    return g


def _mcp(gate, tool, **tool_input):
    return {"session_id": "s", "cwd": str(gate.project), "tool_name": tool, "tool_input": tool_input}


def _decision(answer):
    return (answer.get("hookSpecificOutput") or {}).get("decision", {}).get("behavior", "defer")


def _level(gate, key="mcp:github"):
    return agent_repo.get_license(gate.conn, "shop-api", key)["level"]


def _earn(gate, key, level):
    agent_repo.get_license(gate.conn, "shop-api", key)
    agent_repo.set_level(gate.conn, "shop-api", key, level)


def _write_file_policy(gate, text):
    path = gate.project / ".solo-license" / "policy.toml"
    path.parent.mkdir(exist_ok=True)
    path.write_text(text)


def _approve_and_run(gate, tool, **tool_input):
    answer = gate.permission(_mcp(gate, tool, **tool_input))
    gate.tool_result(_mcp(gate, tool, **tool_input), failed=False)
    return answer


# --- policy: tool rules ------------------------------------------------------------

def test_tool_rules_parse_from_the_team_file(gate):
    _write_file_policy(gate, '[tools."mcp__github__*"]\nrisk = "write"\n\n'
                             '[tools."mcp__aws__delete_*"]\nrisk = "destructive"\nforbidden = true\n\n'
                             '[tools."mcp__github__merge_*"]\nceiling = 1\n')
    rules = policy.effective(gate.conn, "shop-api", gate.project)
    assert not rules.freeze
    assert policy.tool_risk(rules, "mcp__github__list_issues") == "write"   # the rule beats the verb
    assert policy.tool_ceiling(rules, "mcp__github__list_issues") == 1
    assert policy.tool_ceiling(rules, "mcp__github__merge_pull_request") == 1  # the team said otherwise
    assert policy.denied(rules, "mcp__aws__delete_bucket", {}, gate.project)
    assert not policy.denied(rules, "mcp__aws__list_buckets", {}, gate.project)
    assert rules.to_json()["tools"]["mcp__aws__delete_*"] == {"risk": "destructive", "forbidden": True}


def test_built_in_tool_defaults_follow_the_verb():
    rules = policy.merge()
    assert policy.tool_ceiling(rules, "mcp__github__list_issues") == 2
    assert policy.tool_ceiling(rules, "mcp__github__create_issue") == 1
    assert policy.tool_ceiling(rules, "mcp__github__merge_pull_request") == 0
    assert policy.ceiling(rules, "mcp:github", "mcp__github__list_issues") == 2
    assert rules.ceilings["mcp:github"] == 2  # a server no policy names still has its class ceiling


def test_matching_rules_combine_strictly_across_layers(gate):
    _write_file_policy(gate, '[tools."mcp__github__merge_*"]\nrisk = "destructive"\n')
    policy.save_local(gate.conn, "shop-api", {"tools": {"mcp__github__*": {"ceiling": 2}}})
    rules = policy.effective(gate.conn, "shop-api", gate.project)
    assert policy.tool_ceiling(rules, "mcp__github__merge_pull_request") == 0
    assert policy.tool_ceiling(rules, "mcp__github__list_issues") == 2


def test_a_class_ceiling_for_an_mcp_server_caps_every_tool(gate):
    _write_file_policy(gate, '[classes]\n"mcp:github" = { max = 1 }\n')
    rules = policy.effective(gate.conn, "shop-api", gate.project)
    assert policy.ceiling(rules, "mcp:github", "mcp__github__list_issues") == 1
    assert policy.ceiling(rules, "mcp:linear", "mcp__linear__list_issues") == 2


@pytest.mark.parametrize("body", [
    '[tools."mcp__x__*"]\nrisk = "dangerous"\n',
    '[tools."mcp__x__*"]\nceiling = 3\n',
    '[tools."mcp__x__*"]\nforbidden = "yes"\n',
    '[tools."mcp__x__*"]\nrsik = "read"\n',
    '[tools]\n"mcp__x__*" = "read"\n',
])
def test_a_bad_tool_rule_freezes_instead_of_loosening(gate, body):
    _write_file_policy(gate, body)
    assert policy.effective(gate.conn, "shop-api", gate.project).freeze


def test_freezing_keeps_this_machines_tool_rules(gate, harness, tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from sololicense.api import app as app_module
    from sololicense.db.database import init_db
    from sololicense.security import Actor, Role

    conn = init_db(tmp_path / "policy.db", check_same_thread=False)
    threaded = CodingGate(conn, harness.tracer, GitLedger(repo_root=harness.repo),
                          jev_client=JevClient(), checkpoint_lookup=lambda cwd, session: None)
    agent_repo.ensure_repo(conn, "shop-api", str(gate.project))
    conn.commit()

    class Ctx:
        coding_gate = threaded

    Ctx.conn = conn
    monkeypatch.setattr(app_module, "get_context", lambda: Ctx)
    app_module.app.dependency_overrides[app_module.current_actor] = lambda: Actor(actor_id="human:j", role=Role.ADMIN)
    try:
        client = TestClient(app_module.app)
        body = client.put("/api/coding/policy", json={
            "repo": "shop-api", "tools": {"mcp__aws__*": {"forbidden": True}}}).json()
        assert body["effective"]["tools"]["mcp__aws__*"] == {"forbidden": True}
        assert body["tool_defaults"] == {"read": 2, "write": 1, "destructive": 0}
        bad = client.put("/api/coding/policy", json={"repo": "shop-api", "tools": {"mcp__x__*": {"risk": "bad"}}})
        assert bad.status_code == 422
        client.post("/api/coding/freeze", json={"repo": "shop-api", "enabled": True})
        kept = client.get("/api/coding/policy", params={"repo": "shop-api"}).json()
        assert kept["local"]["tools"] == {"mcp__aws__*": {"forbidden": True}} and kept["local"]["freeze"]
        events = [r["reason"] for r in conn.execute("SELECT reason FROM agent_events WHERE kind = 'policy'")]
        assert any("1 tool rule" in e for e in events)
    finally:
        app_module.app.dependency_overrides.clear()


# --- the gate ----------------------------------------------------------------------

def test_a_read_tool_earns_its_server_up_to_l2(gate):
    """The demo: GitHub MCP list_issues earns L2, then runs on its own."""
    assert _decision(gate.permission(_mcp(gate, "mcp__github__list_issues", repo="shop"))) == "defer"
    for page in range(30):
        if _level(gate) == 2:
            break
        _approve_and_run(gate, "mcp__github__list_issues", repo="shop", page=page)
    assert _level(gate) == 2
    assert _decision(gate.permission(_mcp(gate, "mcp__github__get_issue", number=4))) == "allow"
    # Its own license: another server starts from zero.
    assert _decision(gate.permission(_mcp(gate, "mcp__linear__list_issues"))) == "defer"
    log = subprocess.run(["git", "log", "--format=%s"], cwd=gate.ledger._repo_root,
                         capture_output=True, text=True, check=True).stdout
    assert "license(mcp:github@shop-api): promote L1 -> L2" in log


def test_destructive_tools_always_ask_even_at_l2(gate):
    """The demo: merge_pull_request always asks."""
    _earn(gate, "mcp:github", 2)
    answer = gate.permission(_mcp(gate, "mcp__github__merge_pull_request", pull_number=7))
    assert _decision(answer) == "defer"
    assert "merge_pull_request" in answer["systemMessage"] and "always asks" in answer["systemMessage"]
    pre = gate.pre_tool(_mcp(gate, "mcp__github__merge_pull_request", pull_number=7))
    assert pre["hookSpecificOutput"]["permissionDecision"] == "ask"  # bypass mode asks too
    assert gate.pre_tool(_mcp(gate, "mcp__github__list_issues")) == {}


def test_write_tools_run_alone_only_once_a_person_approved_that_tool(gate):
    _earn(gate, "mcp:github", 2)
    assert _decision(gate.permission(_mcp(gate, "mcp__github__create_issue", title="x"))) == "defer"
    gate.tool_result(_mcp(gate, "mcp__github__create_issue", title="x"), failed=False)  # the person said yes
    assert _decision(gate.permission(_mcp(gate, "mcp__github__create_issue", title="y"))) == "allow"
    assert _decision(gate.permission(_mcp(gate, "mcp__github__update_issue", number=1))) == "defer"


def test_the_team_file_can_let_a_destructive_tool_earn(gate):
    _write_file_policy(gate, '[tools."mcp__github__merge_pull_request"]\nrisk = "write"\n')
    _earn(gate, "mcp:github", 2)
    agent_repo.approve_pattern(gate.conn, "shop-api", "mcp:github", "mcp__github__merge_pull_request")
    assert _decision(gate.permission(_mcp(gate, "mcp__github__merge_pull_request"))) == "allow"


def test_forbidden_mcp_tools_are_denied_in_bypass_mode_too(gate):
    _write_file_policy(gate, '[tools."mcp__aws__*"]\nforbidden = true\n')
    _earn(gate, "mcp:aws", 2)
    answer = gate.pre_tool(_mcp(gate, "mcp__aws__list_buckets"))
    out = answer["hookSpecificOutput"]
    assert out["permissionDecision"] == "deny" and "mcp__aws__*" in out["permissionDecisionReason"]
    row = gate.conn.execute("SELECT action_class, decided_by FROM agent_decisions ORDER BY id DESC").fetchone()
    assert (row["action_class"], row["decided_by"]) == ("mcp:aws", "policy")
    assert _level(gate, "mcp:aws") == 0  # reaching for a forbidden tool costs the license


def test_a_failed_write_demotes_the_server_but_a_failed_read_does_not(gate):
    _earn(gate, "mcp:github", 2)
    gate.permission(_mcp(gate, "mcp__github__list_issues"))
    gate.tool_result(_mcp(gate, "mcp__github__list_issues") | {"error": "404"}, failed=True)
    assert _level(gate) == 2
    agent_repo.approve_pattern(gate.conn, "shop-api", "mcp:github", "mcp__github__create_issue")
    gate.permission(_mcp(gate, "mcp__github__create_issue"))
    gate.tool_result(_mcp(gate, "mcp__github__create_issue") | {"error": "422"}, failed=True)
    assert _level(gate) == 0


def test_spans_carry_the_mcp_server_and_tool(gate):
    gate.permission(_mcp(gate, "mcp__github__merge_pull_request", pull_number=7))
    turn = agent_repo.current_turn(gate.conn, "s")
    span = next(s for s in gate._traces[turn["id"]].spans if s.name.startswith("gate."))
    assert span.attributes["mcp_server"] == "github"
    assert span.attributes["mcp_tool"] == "merge_pull_request"
    assert span.attributes["action_class"] == "mcp:github"


def test_licenses_list_mcp_classes_with_a_readable_label(gate, harness):
    from sololicense.api.app import coding_payload

    _earn(gate, "mcp:github", 1)

    class Ctx:
        conn = gate.conn
        coding_gate = gate

    lic = next(item for item in coding_payload(Ctx)["licenses"] if item["action_class"] == "mcp:github")
    assert lic["label"] == "GitHub (MCP)" and lic["max_level"] == 2 and lic["mcp_server"] == "github"
