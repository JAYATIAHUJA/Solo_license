"""Principal-aware coding-agent trust."""

from __future__ import annotations

import sqlite3

from sololicense.coding import agents
from sololicense.coding import policy
from sololicense.coding.gate import CodingGate
from sololicense.coding.jev import JevClient
from sololicense.db.database import init_db
from sololicense.db.repositories import agent as agent_repo
from sololicense.services.git_ledger import GitLedger


def _tool_event(project, *, session="s1", principal=None, **extra):
    event = {
        "session_id": session,
        "cwd": str(project),
        "permission_mode": "default",
        "tool_name": "Bash",
        "tool_input": {"command": "npm install left-pad"},
        **extra,
    }
    if principal:
        event["_principal"] = principal
    return event


def test_native_payloads_identify_subagents_without_affecting_main_sessions():
    _, claude = agents.normalize("claude-code", "PreToolUse", {
        "session_id": "claude-sub",
        "cwd": "/repo",
        "agent_id": "agent-123",
        "agent_type": "Explore",
        "tool_name": "Bash",
        "tool_input": {"command": "npm test"},
    })
    _, cursor = agents.normalize("cursor", "beforeShellExecution", {
        "conversation_id": "cursor-sub",
        "cwd": "/repo",
        "subagent_type": "researcher",
        "command": "npm test",
    })
    _, codex = agents.normalize("codex", "PermissionRequest", {
        "session_id": "codex-main",
        "cwd": "/repo",
        "tool_name": "Bash",
        "tool_input": {"command": "npm test"},
    })

    assert claude["principal"] == "subagent:Explore"
    assert cursor["principal"] == "subagent:researcher"
    assert codex["principal"] == "main"


def test_legacy_license_rows_migrate_to_main_principal(tmp_path):
    db = tmp_path / "legacy.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE agent_licenses (repo TEXT NOT NULL, action_class TEXT NOT NULL, level INTEGER NOT NULL DEFAULT 0, successes INTEGER NOT NULL DEFAULT 0, failures INTEGER NOT NULL DEFAULT 0, successes_at_level INTEGER NOT NULL DEFAULT 0, demoted_from INTEGER, updated_at TEXT NOT NULL DEFAULT (datetime('now')), PRIMARY KEY (repo, action_class))")
    conn.execute("INSERT INTO agent_licenses (repo, action_class, level) VALUES ('shop-api', 'install-dep', 2)")
    conn.commit()
    conn.close()

    migrated = init_db(db)
    columns = {row[1] for row in migrated.execute("PRAGMA table_info(agent_licenses)")}
    row = migrated.execute("SELECT principal, level FROM agent_licenses WHERE repo = 'shop-api'").fetchone()

    assert "principal" in columns
    assert tuple(row) == ("main", 2)


def test_subagent_falls_back_to_main_at_lower_ceiling(harness, tmp_path):
    project = tmp_path / "shop-api"
    project.mkdir()
    gate = CodingGate(harness.conn, harness.tracer, GitLedger(repo_root=harness.repo), jev_client=JevClient())

    main = agent_repo.get_license(harness.conn, "shop-api", "install-dep")
    agent_repo.set_level(harness.conn, "shop-api", "install-dep", 2)
    inherited = agent_repo.effective_license(harness.conn, "shop-api", "install-dep", "subagent:Explore", max_level=1)

    assert main["principal"] == "main"
    assert inherited["principal"] == "subagent:Explore"
    assert inherited["level"] == 1


def test_policy_can_lower_the_subagent_ceiling(harness):
    policy.save_local(harness.conn, "shop-api", {"subagents": {"max": 0}})

    rules = policy.effective(harness.conn, "shop-api", ".")

    assert rules.subagent_max == 0


def test_subagent_failure_demotes_only_its_own_license(harness, tmp_path):
    project = tmp_path / "shop-api"
    project.mkdir()
    gate = CodingGate(harness.conn, harness.tracer, GitLedger(repo_root=harness.repo), jev_client=JevClient())
    agent_repo.get_license(harness.conn, "shop-api", "install-dep", principal="main")
    agent_repo.get_license(harness.conn, "shop-api", "install-dep", principal="subagent:Explore")
    agent_repo.set_level(harness.conn, "shop-api", "install-dep", 2, principal="main")
    agent_repo.set_level(harness.conn, "shop-api", "install-dep", 2, principal="subagent:Explore")
    agent_repo.approve_pattern(harness.conn, "shop-api", "install-dep", "npm install")

    sub = _tool_event(project, session="sub", principal="subagent:Explore")
    gate.user_prompt({"session_id": "sub", "cwd": str(project), "prompt": "install a dependency",
                      "_principal": "subagent:Explore", "_agent": "claude-code"})
    answer = gate.permission(sub)
    assert answer["hookSpecificOutput"]["decision"]["behavior"] == "allow"
    gate.tool_result(sub | {"error": "Exit code 1"}, failed=True)

    assert agent_repo.get_license(harness.conn, "shop-api", "install-dep", principal="subagent:Explore")["level"] == 0
    assert agent_repo.get_license(harness.conn, "shop-api", "install-dep", principal="main")["level"] == 2
    event = harness.conn.execute("SELECT principal, kind FROM agent_events ORDER BY id DESC LIMIT 1").fetchone()
    assert tuple(event) == ("subagent:Explore", "demote")
