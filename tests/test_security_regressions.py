"""The five behaviours a judge (or an attacker) checks first. Each was either a
real hole or a headline claim; each is pinned here so it cannot regress."""

from __future__ import annotations

import io
import json
import subprocess

import pytest

from sololicense.coding import shim
from sololicense.coding.actions import classify_command
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
    (project / "README.md").write_text("demo\n")
    subprocess.run(["git", "add", "."], cwd=project, check=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=project, check=True)
    gate = CodingGate(harness.conn, harness.tracer, GitLedger(repo_root=harness.repo),
                      jev_client=JevClient(), checkpoint_lookup=lambda cwd, session: None)
    gate.project = project
    return gate


def _bash(gate, command, **extra):
    return {"session_id": "s1", "cwd": str(gate.project), "tool_name": "Bash",
            "tool_input": {"command": command}, "_prompt_only": True, **extra}


def _decision(answer):
    return ((answer.get("hookSpecificOutput") or {}).get("decision") or {})


@pytest.mark.parametrize("command", [
    "echo pwned >> ~/.ssh/authorized_keys",
    "tee -a ~/.bashrc",
    "cp key ~/.ssh/id_rsa",
    "echo $PATH > /etc/environment",
])
def test_writing_credentials_or_startup_files_is_never_a_read(command):
    result = classify_command(command)
    assert result.action_class != "read"
    assert result.hard_deny == "writes to credentials or shell start-up files"


@pytest.mark.parametrize("command", ["echo x > notes.txt", "cat a.txt >> b.txt", "sed -i s/a/b/ app.js"])
def test_a_redirect_into_a_file_is_an_edit(command):
    assert classify_command(command).action_class == "file-edit"


@pytest.mark.parametrize("command", ["npm test 2>&1", "npm test > /dev/null", "echo 'a > b'", "ls -la"])
def test_harmless_redirects_and_quotes_stay_what_they_were(command):
    assert classify_command(command).action_class in ("read", "test-run")


@pytest.mark.parametrize("command", [
    "git push origin +main", "git push origin +HEAD:main", "git push -f origin main",
    "git push --force origin main", "git push --force-with-lease origin master",
])
def test_every_way_to_force_push_main_is_denied(gate, command):
    gate.user_prompt({"session_id": "s1", "cwd": str(gate.project), "prompt": "ship it"})
    decision = _decision(gate.permission(_bash(gate, command)))
    assert decision["behavior"] == "deny"
    assert "force-pushes a protected branch" in decision["message"]  # a reason the agent can act on


def test_three_approved_verified_runs_earn_npm_test_and_the_fourth_runs_alone(gate):
    gate.user_prompt({"session_id": "s1", "cwd": str(gate.project), "prompt": "run the tests"})
    for _ in range(3):
        assert _decision(gate.permission(_bash(gate, "npm test"))).get("behavior") != "allow"
        gate.tool_result(_bash(gate, "npm test"), failed=False)  # it ran, so the person said yes
    assert agent_repo.get_license(gate.conn, "shop-api", "test-run")["level"] >= 1
    assert _decision(gate.permission(_bash(gate, "npm test")))["behavior"] == "allow"


def test_a_gate_that_is_down_defers_and_never_allows(monkeypatch, capsys):
    monkeypatch.setenv("SOLO_LICENSE_URL", "http://127.0.0.1:9")  # nothing listens here
    monkeypatch.setenv("SOLO_HOOK_TIMEOUT", "2")
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(
        {"tool_name": "Bash", "tool_input": {"command": "git push --force origin main"}})))
    assert shim.main(["hook.py", "codex", "PermissionRequest"]) == 0
    out = capsys.readouterr().out
    assert "allow" not in out  # no answer at all: the agent's own settings decide


def test_the_digest_jev_reads_carries_what_the_turn_has_done(gate):
    from sololicense.coding import digest

    gate.user_prompt({"session_id": "s1", "cwd": str(gate.project), "prompt": "fix the cart"})
    edit = {"session_id": "s1", "cwd": str(gate.project), "tool_name": "Edit", "_prompt_only": True,
            "tool_input": {"file_path": "cart.js", "old_string": "a", "new_string": "b"}}
    gate.permission(edit)
    gate.tool_result(edit, failed=False)
    bash = _bash(gate, "npm install left-pad")
    gate.permission(bash)
    gate.tool_result({**bash, "error": "npm ERR! 404"}, failed=True)
    turn = digest.build(gate.conn, "s1", repo="shop-api")["turn"]
    assert turn["files_touched"] == ["cart.js"]
    assert turn["failures"] == ["npm install left-pad"]
