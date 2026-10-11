"""One gate, many agents: native payloads in, native answers out."""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

from sololicense.cli import agent_prompt
from sololicense.coding import agents
from sololicense.coding.install import install

ALLOW = {"hookSpecificOutput": {"hookEventName": "PermissionRequest", "decision": {"behavior": "allow"}}}
DENY = {"hookSpecificOutput": {"hookEventName": "PermissionRequest",
                               "decision": {"behavior": "deny", "message": "Blocked: x."}}}
DEFER = {"systemMessage": "Run tests is at L0."}


@pytest.mark.parametrize("agent, event, payload, tool, value", [
    ("codex", "PermissionRequest", {"session_id": "s", "cwd": "/r", "tool_name": "Bash",
                                    "tool_input": {"command": "npm test"}}, "Bash", "npm test"),
    ("codex", "PermissionRequest", {"tool_name": "apply_patch",
                                    "tool_input": {"command": "*** Begin Patch\n*** Update File: src/a.py\n"}},
     "Edit", "src/a.py"),
    ("cursor", "beforeShellExecution", {"conversation_id": "c", "command": "pytest", "cwd": "/r"}, "Bash", "pytest"),
    ("cursor", "afterFileEdit", {"conversation_id": "c", "file_path": "/r/a.ts"}, "Edit", "/r/a.ts"),
    ("gemini", "BeforeTool", {"tool_name": "run_shell_command", "tool_input": {"command": "ls"}}, "Bash", "ls"),
    ("gemini", "BeforeTool", {"tool_name": "write_file", "tool_input": {"file_path": "a.py"}}, "Edit", "a.py"),
    ("antigravity", "PreToolUse", {"conversationId": "a", "workspacePaths": ["/r"],
                                   "toolCall": {"name": "run_command", "args": {"CommandLine": "make"}}}, "Bash", "make"),
    ("windsurf", "pre_run_command", {"trajectory_id": "w", "tool_info": {"command_line": "npm i"}}, "Bash", "npm i"),
    ("copilot", "preToolUse", {"sessionId": "p", "toolName": "bash", "toolArgs": '{"command": "go test"}'},
     "Bash", "go test"),
    ("grok", "PreToolUse", {"sessionId": "g", "toolName": "Bash", "toolInput": {"command": "cargo test"}},
     "Bash", "cargo test"),
    ("cline", "PreToolUse", {"taskId": "t", "preToolUse": {"toolName": "execute_command",
                                                           "parameters": {"command": "npm run build"}}},
     "Bash", "npm run build"),
    ("opencode", "tool.execute.before", {"sessionID": "o", "tool_name": "bash", "tool_input": {"command": "ls"}},
     "Bash", "ls"),
])
def test_native_tool_calls_become_the_gates_common_shape(agent, event, payload, tool, value):
    gate_event, body = agents.normalize(agent, event, payload)
    assert gate_event == ("post-tool" if event == "afterFileEdit" else "permission")
    assert body["tool_name"] == tool
    assert value in body["tool_input"].values()
    assert body["session_id"]


def test_a_failed_tool_result_is_reported_as_a_failure():
    event, body = agents.normalize("codex", "PostToolUse", {"tool_name": "Bash", "tool_input": {"command": "npm i"},
                                                            "tool_response": {"exit_code": 1}})
    assert event == "post-tool-failure"


def test_unknown_events_are_ignored():
    assert agents.normalize("cursor", "beforeReadFile", {}) is None
    assert agents.render("cursor", "beforeReadFile", ALLOW).body is None


@pytest.mark.parametrize("agent, event, expected_allow, expected_deny", [
    ("codex", "PermissionRequest", {"hookSpecificOutput": {"hookEventName": "PermissionRequest",
                                                           "decision": {"behavior": "allow"}}}, None),
    ("cursor", "beforeShellExecution", None, None),
    ("copilot", "preToolUse", None, None),
])
def test_allow_and_deny_in_each_agents_words(agent, event, expected_allow, expected_deny):
    allowed, denied = agents.render(agent, event, ALLOW), agents.render(agent, event, DENY)
    if expected_allow:
        assert allowed.body == expected_allow
    text = json.dumps(denied.body) + denied.stderr
    assert "deny" in text or denied.exit == 2


def test_exit_code_agents_block_with_exit_two_and_defer_with_nothing():
    for agent, event in (("windsurf", "pre_run_command"), ("kiro", "PreToolUse"), ("gemini", "BeforeTool")):
        assert agents.render(agent, event, DENY).exit == 2
        deferred = agents.render(agent, event, DEFER)
        assert deferred.exit == 0 and deferred.body is None


def test_ask_is_always_deferred_to_the_agents_own_settings():
    for spec in agents.AGENTS.values():
        for native, gate_event in spec.events.items():
            if gate_event == "permission":
                native_answer = agents.render(spec.key, native, DEFER)
                assert native_answer.body is None and native_answer.exit == 0, spec.key


def test_a_turn_sent_back_in_each_agents_words():
    block = {"decision": "block", "reason": "over-editing"}
    assert agents.render("codex", "Stop", block).body == block
    assert agents.render("cursor", "stop", block).body == {"followup_message": "over-editing"}
    assert agents.render("gemini", "AfterAgent", block).body["decision"] == "deny"
    assert agents.render("antigravity", "Stop", block).body["decision"] == "continue"
    assert agents.render("windsurf", "post_cascade_response", block).body is None


def test_aliases_and_unsupported_agents():
    assert agents.resolve("glm").key == "claude-code"
    assert agents.resolve("groq").key == "opencode"
    with pytest.raises(KeyError, match="no pre-action hooks"):
        agents.resolve("aider")


def test_install_writes_every_agent_and_keeps_existing_hooks(tmp_path):
    (tmp_path / ".cursor").mkdir()
    (tmp_path / ".cursor" / "hooks.json").write_text(json.dumps(
        {"version": 1, "hooks": {"stop": [{"command": "entire hooks cursor stop"}]}}))
    for key in agents.AGENTS:
        install(tmp_path, "http://127.0.0.1:8000", key)
        install(tmp_path, "http://127.0.0.1:8000", key)  # idempotent
    cursor = json.loads((tmp_path / ".cursor" / "hooks.json").read_text())
    assert [h["command"] for h in cursor["hooks"]["stop"]][0] == "entire hooks cursor stop"
    assert len(cursor["hooks"]["stop"]) == 2
    assert (tmp_path / ".solo-license" / "hook.py").exists()
    codex = json.loads((tmp_path / ".codex" / "hooks.json").read_text())
    assert "codex PermissionRequest" in codex["hooks"]["PermissionRequest"][0]["hooks"][0]["command"]
    grok = json.loads((tmp_path / ".grok" / "hooks" / "solo-license.json").read_text())
    assert grok["hooks"]["PreToolUse"][0]["hooks"][0]["url"].endswith("/api/hooks/grok/PreToolUse")
    assert "tool.execute.before" in (tmp_path / ".opencode" / "plugins" / "solo-license.ts").read_text()
    assert (tmp_path / ".clinerules" / "hooks" / "PreToolUse").exists()


def test_the_shim_defers_when_the_gate_is_down(tmp_path):
    install(tmp_path, "http://127.0.0.1:8000", "codex")
    result = subprocess.run(
        [sys.executable, str(tmp_path / ".solo-license" / "hook.py"), "codex", "PermissionRequest"],
        input="{}", capture_output=True, text=True, env={"SOLO_LICENSE_URL": "http://127.0.0.1:9", "SYSTEMROOT": "C:\\Windows"},
        timeout=30,
    )
    assert result.returncode == 0 and result.stdout == ""


def test_agent_prompt_names_the_one_liner_and_asks_before_installing_uv():
    text = agent_prompt("codex")
    assert "uv tool install git+https://github.com/JAYATIAHUJA/Solo_license" in text
    assert "solo-license init --agent codex" in text and "Ask me before" in text


def test_the_installed_command_really_runs(tmp_path):
    """Run the exact command string the installer writes, through a shell."""
    repo = tmp_path / "my repo"   # a space in the path, like 'solo lincense'
    repo.mkdir()
    install(repo, "http://127.0.0.1:9", "codex")
    hooks = json.loads((repo / ".codex" / "hooks.json").read_text())
    command = hooks["hooks"]["PermissionRequest"][0]["hooks"][0]["command"]
    assert command.count('"') == 4
    result = subprocess.run(command.split(" #")[0], shell=True, input="{}", capture_output=True,
                            text=True, timeout=30, env={**__import__("os").environ, "SOLO_LICENSE_URL": "http://127.0.0.1:9"})
    assert result.returncode == 0, result.stderr


def test_decisions_only_take_known_columns(tmp_path):
    from sololicense.db.database import init_db
    from sololicense.db.repositories import agent as agent_repo

    conn = init_db(tmp_path / "x.db")
    with pytest.raises(ValueError):
        agent_repo.insert_decision(conn, session_id="s", **{"repo) VALUES (1); DROP TABLE runs; --": "x"})


def test_hook_route_rejects_malformed_agent_and_event_names():
    from fastapi.testclient import TestClient

    from sololicense.api.app import app

    client = TestClient(app)
    assert client.post("/api/hooks/codex/..%2F..%2Fetc", json={}).status_code in (404, 422)
    assert client.post("/api/hooks/Codex;rm/PreToolUse", json={}).status_code == 422
    assert client.post("/api/hooks/codex/Pre Tool", json={}).status_code == 422



@pytest.mark.parametrize("name", ["repo$(whoami)", "repo`id`", "repo;rm", "repo%PATH%", "repo'x"])
def test_paths_a_shell_would_expand_are_refused(tmp_path, name):
    """Trail #26 finding: a repo path must never become shell code in a hook."""
    repo = tmp_path / name
    repo.mkdir()
    for agent in ("cline", "codex", "cursor"):
        with pytest.raises(SystemExit, match="shell characters"):
            install(repo, "http://127.0.0.1:8000", agent)


def test_cline_scripts_single_quote_their_paths(tmp_path):
    repo = tmp_path / "my repo"
    repo.mkdir()
    install(repo, "http://127.0.0.1:8000", "cline")
    script = (repo / ".clinerules" / "hooks" / "PreToolUse").read_text()
    assert "exec '" in script and "my repo/.solo-license/hook.py'" in script.replace("\\", "/")


@pytest.mark.parametrize("url", ["http://x/${process.exit(1)}", "javascript:alert(1)", "http://a`b`", 'http://a"+x+"'])
def test_gate_urls_that_are_not_plain_http_are_refused(tmp_path, url):
    with pytest.raises(SystemExit, match="plain http"):
        install(tmp_path, url, "opencode")


def test_opencode_plugin_embeds_the_url_as_a_json_string(tmp_path):
    install(tmp_path, "http://127.0.0.1:8000", "opencode")
    plugin = (tmp_path / ".opencode" / "plugins" / "solo-license.ts").read_text()
    assert 'process.env.SOLO_LICENSE_URL ?? "http://127.0.0.1:8000"' in plugin
