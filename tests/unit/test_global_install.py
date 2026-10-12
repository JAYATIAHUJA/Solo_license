"""``solo-license init --global``: user-level hooks, always against a fake home."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from sololicense import cli
from sololicense.coding import agents, shim
from sololicense.coding import global_install as gi

URL = "http://127.0.0.1:8000"


@pytest.fixture
def home(tmp_path, monkeypatch) -> Path:
    home = tmp_path / "my home"   # a space, like C:\Users\First Last
    home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    for var in ("SOLO_LICENSE_HOME", "CODEX_HOME", "COPILOT_HOME", "CLAUDE_CONFIG_DIR", "SOLO_LICENSE_URL"):
        monkeypatch.delenv(var, raising=False)
    return home


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _snapshot(root: Path) -> dict[str, str]:
    return {str(p.relative_to(root)): p.read_text(encoding="utf-8") for p in root.rglob("*") if p.is_file()}


def test_global_paths_are_the_documented_user_level_locations(home):
    assert gi.global_path("claude-code") == home / ".claude" / "settings.json"
    assert gi.global_path("codex") == home / ".codex" / "hooks.json"
    assert gi.global_path("cursor") == home / ".cursor" / "hooks.json"
    assert gi.global_path("gemini") == home / ".gemini" / "settings.json"
    assert gi.global_path("copilot") == home / ".copilot" / "hooks" / "solo-license.json"
    assert gi.global_path("grok") == home / ".grok" / "hooks" / "solo-license.json"
    assert gi.global_path("windsurf") == home / ".codeium" / "windsurf" / "hooks.json"
    assert gi.global_path("kiro") == home / ".kiro" / "hooks" / "solo-license.json"
    assert gi.global_path("cline") == home / "Documents" / "Cline" / "Hooks"
    assert gi.global_path("opencode") == home / ".config" / "opencode" / "plugins" / "solo-license.ts"
    assert set(gi.GLOBAL_DOCS) == set(agents.AGENTS)


def test_agent_home_variables_are_respected(home, monkeypatch):
    monkeypatch.setenv("CODEX_HOME", str(home / "cx"))
    monkeypatch.setenv("COPILOT_HOME", str(home / "cp"))
    assert gi.global_path("codex") == home / "cx" / "hooks.json"
    assert gi.global_path("copilot") == home / "cp" / "hooks" / "solo-license.json"


def test_init_global_writes_every_agent_and_one_shim(home):
    gi.apply(gi.plan(list(agents.AGENTS), URL))
    shim_path = home / ".solo-license" / "hook.py"
    assert shim_path.read_text(encoding="utf-8") == Path(shim.__file__).read_text(encoding="utf-8")

    claude = _json(home / ".claude" / "settings.json")
    assert claude["hooks"]["PermissionRequest"][0]["hooks"][0]["url"] == f"{URL}/api/hooks/permission"
    codex = _json(home / ".codex" / "hooks.json")
    command = codex["hooks"]["PermissionRequest"][0]["hooks"][0]["command"]
    assert f'"{shim_path}" codex PermissionRequest' in command
    assert _json(home / ".cursor" / "hooks.json")["version"] == 1
    assert "BeforeTool" in _json(home / ".gemini" / "settings.json")["hooks"]
    assert "solo-license" in _json(home / ".gemini" / "config" / "hooks.json")
    assert _json(home / ".grok" / "hooks" / "solo-license.json")["hooks"]["PreToolUse"][0]["hooks"][0]["url"] \
        .endswith("/api/hooks/grok/PreToolUse")
    windsurf = _json(home / ".codeium" / "windsurf" / "hooks.json")["hooks"]["pre_run_command"][0]
    assert windsurf["powershell"].startswith("& ")
    assert (home / "Documents" / "Cline" / "Hooks" / "PreToolUse").exists()
    assert "tool.execute.before" in (home / ".config" / "opencode" / "plugins" / "solo-license.ts").read_text()


def test_init_global_keeps_other_hooks_and_settings_and_is_idempotent(home):
    claude = home / ".claude" / "settings.json"
    claude.parent.mkdir()
    claude.write_text(json.dumps({"model": "opus", "hooks": {"Stop": [
        {"hooks": [{"type": "command", "command": "entire hooks claude-code stop"}]}]}}))
    cursor = home / ".cursor" / "hooks.json"
    cursor.parent.mkdir()
    cursor.write_text(json.dumps({"version": 1, "hooks": {"stop": [{"command": "entire hooks cursor stop"}]}}))

    gi.apply(gi.plan(["claude-code", "cursor"], URL))
    first = _snapshot(home)
    assert gi.plan(["claude-code", "cursor"], URL) == []      # nothing left to change
    gi.apply(gi.plan(["claude-code", "cursor"], URL))
    assert _snapshot(home) == first

    data = _json(claude)
    assert data["model"] == "opus"
    assert data["hooks"]["Stop"][0]["hooks"][0]["command"] == "entire hooks claude-code stop"
    assert len(data["hooks"]["Stop"]) == 2
    assert [h["command"] for h in _json(cursor)["hooks"]["stop"]][0] == "entire hooks cursor stop"


def test_dry_run_shows_a_diff_and_writes_nothing(home, capsys):
    assert cli.main(["init", "--global", "--agent", "codex", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert str(home / ".codex" / "hooks.json") in out
    assert '+    "PermissionRequest": [' in out
    assert "hook.py" in out
    assert not any(home.rglob("*"))


def test_remove_takes_out_only_our_entries(home):
    claude = home / ".claude" / "settings.json"
    claude.parent.mkdir()
    claude.write_text(json.dumps({"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "entire x"}]}]}}))
    every = list(agents.AGENTS)
    gi.apply(gi.plan(every, URL))
    gi.apply(gi.plan(every, URL, remove=True))

    assert _json(claude) == {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "entire x"}]}]}}
    assert not (home / ".cursor" / "hooks.json").exists()          # it held only our hooks
    assert not (home / ".grok" / "hooks" / "solo-license.json").exists()
    assert not (home / "Documents" / "Cline" / "Hooks" / "PreToolUse").exists()
    assert not (home / ".solo-license" / "hook.py").exists()
    assert not (home / ".codex" / "prompts" / "trust.md").exists()
    assert gi.plan(every, URL, remove=True) == []


def test_removing_one_agent_keeps_the_shim_the_others_use(home):
    gi.apply(gi.plan(["codex", "cursor"], URL))
    gi.apply(gi.plan(["codex"], URL, remove=True))
    assert (home / ".solo-license" / "hook.py").exists()
    assert (home / ".cursor" / "hooks.json").exists()


def test_codex_prompt_and_cursor_skill_show_trust_levels(home):
    gi.apply(gi.plan(["codex", "cursor"], "http://127.0.0.1:8123"))
    prompt = (home / ".codex" / "prompts" / "trust.md").read_text(encoding="utf-8")
    assert prompt.startswith("---\ndescription:")
    assert "http://127.0.0.1:8123/api/coding?repo=" in prompt
    assert "$" not in prompt          # Codex expands $1 / $NAME placeholders in prompts
    skill = (home / ".cursor" / "skills" / "trust" / "SKILL.md").read_text(encoding="utf-8")
    assert "name: trust" in skill and "http://127.0.0.1:8123/api/coding?repo=" in skill


def test_a_trust_prompt_that_is_not_ours_is_left_alone(home):
    mine = home / ".codex" / "prompts" / "trust.md"
    mine.parent.mkdir(parents=True)
    mine.write_text("my own prompt\n")
    gi.apply(gi.plan(["codex"], URL))
    gi.apply(gi.plan(["codex"], URL, remove=True))
    assert mine.read_text() == "my own prompt\n"


def test_detect_finds_agents_from_their_home_folders(home):
    assert gi.detect() == []
    (home / ".codex").mkdir()
    (home / ".cursor").mkdir()
    assert gi.detect() == ["codex", "cursor"]


def test_cli_init_global_installs_detected_agents(home, capsys):
    (home / ".codex").mkdir()
    assert cli.main(["init", "--global"]) == 0
    out = capsys.readouterr().out
    assert (home / ".codex" / "hooks.json").exists()
    assert not (home / ".claude").exists()
    assert "/hooks" in out and "serve --background" in out


def test_the_global_hook_command_really_runs(home):
    gi.apply(gi.plan(["codex"], "http://127.0.0.1:9"))
    command = _json(home / ".codex" / "hooks.json")["hooks"]["PermissionRequest"][0]["hooks"][0]["command"]
    import os

    result = subprocess.run(command.split(" #")[0], shell=True, input="{}", capture_output=True, text=True,
                            timeout=30, env={**os.environ, "SOLO_LICENSE_URL": "http://127.0.0.1:9"})
    assert result.returncode == 0 and result.stdout == "", result.stderr


def test_a_home_path_a_shell_would_expand_is_refused(tmp_path, monkeypatch):
    bad = tmp_path / "me$(id)"
    bad.mkdir()
    monkeypatch.setattr(Path, "home", lambda: bad)
    monkeypatch.delenv("SOLO_LICENSE_HOME", raising=False)
    with pytest.raises(SystemExit, match="shell characters"):
        gi.plan(["codex"], URL)


def test_the_shim_fills_in_the_working_directory_for_user_level_hooks(monkeypatch, tmp_path):
    monkeypatch.delenv("CURSOR_PROJECT_DIR", raising=False)
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    monkeypatch.delenv("GEMINI_PROJECT_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    assert shim.with_cwd({"tool_name": "x"})["cwd"] == str(tmp_path)
    assert shim.with_cwd({"cwd": "/repo"})["cwd"] == "/repo"
    assert "cwd" not in shim.with_cwd({"workspace_roots": ["/repo"]})
    monkeypatch.setenv("CURSOR_PROJECT_DIR", "/from-cursor")
    assert shim.with_cwd({})["cwd"] == "/from-cursor"


def test_per_repo_init_supports_dry_run_and_remove(tmp_path, home, capsys):
    repo = tmp_path / "repo"
    repo.mkdir()
    assert cli.main(["init", "--agent", "cursor", "--repo", str(repo), "--dry-run"]) == 0
    assert not (repo / ".cursor").exists()
    assert cli.main(["init", "--agent", "cursor", "--repo", str(repo)]) == 0
    assert (repo / ".cursor" / "hooks.json").exists()
    assert cli.main(["init", "--agent", "cursor", "--repo", str(repo), "--remove"]) == 0
    assert not (repo / ".cursor" / "hooks.json").exists()
