"""Subagent lifecycle hooks and policy gates."""

from __future__ import annotations

import json

from sololicense.coding import agents, policy
from sololicense.coding.gate import CodingGate
from sololicense.coding.jev import JevClient
from sololicense.coding.install import install
from sololicense.db.repositories import agent as agent_repo
from sololicense.services.git_ledger import GitLedger


def _gate(harness, project):
    return CodingGate(harness.conn, harness.tracer, GitLedger(repo_root=harness.repo), jev_client=JevClient())


def test_subagent_lifecycle_payloads_normalize_to_gate_events():
    start, start_body = agents.normalize("claude-code", "SubagentStart", {
        "session_id": "s",
        "cwd": "/repo",
        "agent_id": "a1",
        "agent_type": "Explore",
    })
    stop, stop_body = agents.normalize("cursor", "subagentStop", {
        "conversation_id": "s",
        "cwd": "/repo",
        "subagent_type": "researcher",
        "modified_files": ["src/a.py"],
    })

    assert start == agents.SUB_START and start_body["principal"] == "subagent:Explore"
    assert stop == agents.SUB_STOP and stop_body["modified_files"] == ["src/a.py"]


def test_subagent_start_receives_a_license_summary(harness, tmp_path):
    project = tmp_path / "shop-api"
    project.mkdir()
    gate = _gate(harness, project)

    answer = gate.subagent_start({"session_id": "sub", "cwd": str(project),
                                  "_agent": "claude-code", "_principal": "subagent:Explore",
                                  "subagent_type": "Explore"})

    assert "additionalContext" in answer["hookSpecificOutput"]
    assert "subagent:Explore" in answer["hookSpecificOutput"]["additionalContext"]
    turn = agent_repo.current_turn(harness.conn, "sub")
    assert turn["principal"] == "subagent:Explore"


def test_deny_types_block_an_agent_spawn(harness, tmp_path):
    project = tmp_path / "shop-api"
    project.mkdir()
    gate = _gate(harness, project)
    policy.save_local(harness.conn, "shop-api", {"subagents": {"deny_types": ["Explore"]}})
    gate.user_prompt({"session_id": "main", "cwd": str(project), "prompt": "delegate"})

    answer = gate.permission({"session_id": "main", "cwd": str(project), "tool_name": "Agent",
                              "tool_input": {"subagent_type": "Explore"}})

    decision = answer["hookSpecificOutput"]["decision"]
    assert decision["behavior"] == "deny" and "Explore" in decision["message"]


def test_subagent_stop_reuses_turn_verification_and_sends_back_failures(harness, tmp_path):
    project = tmp_path / "shop-api"
    project.mkdir()
    gate = _gate(harness, project)
    gate.verifier = lambda *_: (False, "subagent changed files outside its task", {"blame": ["file-edit"]})
    gate.subagent_start({"session_id": "sub", "cwd": str(project), "_agent": "claude-code",
                         "_principal": "subagent:Explore", "subagent_type": "Explore"})

    answer = gate.subagent_stop({"session_id": "sub", "cwd": str(project),
                                 "_principal": "subagent:Explore", "modified_files": ["src/a.py"]})

    assert answer["decision"] == "block"
    assert "subagent changed files" in answer["reason"]


def test_install_registers_subagent_lifecycle_hooks(tmp_path):
    install(tmp_path, "http://127.0.0.1:8000", "claude-code")
    install(tmp_path, "http://127.0.0.1:8000", "codex")
    install(tmp_path, "http://127.0.0.1:8000", "cursor")

    claude = json.loads((tmp_path / ".claude" / "settings.local.json").read_text())
    codex = json.loads((tmp_path / ".codex" / "hooks.json").read_text())
    cursor = json.loads((tmp_path / ".cursor" / "hooks.json").read_text())
    assert {"SubagentStart", "SubagentStop"} <= set(claude["hooks"])
    assert {"SubagentStart", "SubagentStop"} <= set(codex["hooks"])
    assert {"subagentStart", "subagentStop"} <= set(cursor["hooks"])
