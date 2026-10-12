"""``solo-license doctor``: pass / warn / fail checks, against a fake home."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from sololicense import cli, doctor
from sololicense.coding import global_install as gi
from sololicense.coding.install import install

URL = "http://127.0.0.1:8000"


@pytest.fixture
def home(tmp_path, monkeypatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home)
    for var in ("SOLO_LICENSE_HOME", "CODEX_HOME", "COPILOT_HOME", "CLAUDE_CONFIG_DIR", "SOLO_LICENSE_URL",
                "NEATLOGS_API_KEY", "SOLO_LICENSE_DB"):
        monkeypatch.delenv(var, raising=False)
    return home


@pytest.fixture
def repo(tmp_path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    return repo


def _run(repo, *, up=True, which=None, version=None):
    return doctor.run(repo, URL, get=lambda url: {"agents": []} if up else None,
                      which=which or (lambda name: None), version=version or (lambda exe: ""))


def _by_label(checks):
    return {c.label: c for c in checks}


def test_an_unreachable_gate_fails(home, repo):
    checks = _run(repo, up=False)
    gate = _by_label(checks)["gate"]
    assert gate.level == "fail" and "serve --background" in gate.detail
    assert doctor.exit_code(checks) == 1


def test_no_hooks_anywhere_fails(home, repo):
    checks = _run(repo)
    assert _by_label(checks)["hooks"].level == "fail"


def test_global_hooks_pointing_at_the_gate_pass(home, repo):
    gi.apply(gi.plan(["claude-code", "codex"], URL))
    checks = _by_label(_run(repo))
    assert checks["Claude Code (global)"].level == "pass"
    assert checks["OpenAI Codex CLI (global)"].level == "pass"
    assert "hooks" not in checks


def test_hooks_pointing_at_another_url_fail(home, repo):
    gi.apply(gi.plan(["claude-code"], "http://127.0.0.1:9999"))
    check = _by_label(_run(repo))["Claude Code (global)"]
    assert check.level == "fail" and "9999" in check.detail


def test_a_missing_shim_fails(home, repo):
    gi.apply(gi.plan(["codex"], URL))
    (home / ".solo-license" / "hook.py").unlink()
    check = _by_label(_run(repo))["OpenAI Codex CLI (global)"]
    assert check.level == "fail" and "init --global" in check.detail


def test_a_stale_shim_warns(home, repo):
    gi.apply(gi.plan(["codex"], URL))
    (home / ".solo-license" / "hook.py").write_text("# old\n")
    assert _by_label(_run(repo))["OpenAI Codex CLI (global)"].level == "warn"


def test_repo_and_global_hooks_together_warn_about_double_gating(home, repo):
    gi.apply(gi.plan(["cursor"], URL))
    install(repo, URL, "cursor")
    checks = _by_label(_run(repo))
    assert checks["Cursor (repo)"].level == "pass"
    assert checks["Cursor (global)"].level == "warn"
    assert "twice" in checks["Cursor (global)"].detail


def test_agent_clis_are_listed_with_versions_and_missing_ones_tolerated(home, repo):
    gi.apply(gi.plan(["claude-code"], URL))
    found = {"claude": "/bin/claude", "entire": "/bin/entire"}
    checks = _by_label(_run(repo, which=found.get, version=lambda exe: f"{Path(exe).name} 1.2.3"))
    assert checks["claude"].level == "pass" and "1.2.3" in checks["claude"].detail
    assert checks["codex"].level == "info" and "not found" in checks["codex"].detail
    assert checks["entire"].level == "pass"
    assert doctor.exit_code(list(checks.values())) == 0


def test_missing_entire_and_neatlogs_only_warn(home, repo):
    gi.apply(gi.plan(["claude-code"], URL))
    checks = _by_label(_run(repo))
    assert checks["entire"].level == "warn"
    assert checks["neatlogs"].level == "warn"
    assert doctor.exit_code(list(checks.values())) == 0


def test_neatlogs_key_from_env_or_saved_settings(home, repo, monkeypatch):
    monkeypatch.setenv("NEATLOGS_API_KEY", "nlk-x")
    assert _by_label(_run(repo))["neatlogs"].level == "pass"
    monkeypatch.delenv("NEATLOGS_API_KEY")
    db = home / ".solo-license" / "solo_license.db"
    db.parent.mkdir(parents=True)
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        conn.execute("INSERT INTO settings VALUES ('neatlogs_api_key', 'fernet:abc')")
    assert _by_label(_run(repo))["neatlogs"].level == "pass"


def test_cli_doctor_prints_levels_and_exits_non_zero_on_failure(home, repo, monkeypatch, capsys):
    monkeypatch.setattr(cli, "_get", lambda url, timeout=3.0: None)
    monkeypatch.setattr(doctor.shutil, "which", lambda name: None)
    assert cli.main(["doctor", "--repo", str(repo), "--url", URL]) == 1
    out = capsys.readouterr().out
    assert "FAIL" in out and "gate" in out
