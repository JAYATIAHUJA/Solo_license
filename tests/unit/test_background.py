"""``solo-license serve --background`` / ``stop`` / ``status``, with a fake home."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from sololicense import background, cli


@pytest.fixture
def solo_home(tmp_path, monkeypatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.delenv("SOLO_LICENSE_HOME", raising=False)
    monkeypatch.delenv("SOLO_LICENSE_PORT", raising=False)
    monkeypatch.delenv("SOLO_LICENSE_URL", raising=False)
    return home / ".solo-license"


class FakeProcess:
    pid = 4242

    def poll(self):
        return None


def test_start_detaches_the_gate_and_records_it(solo_home, monkeypatch):
    calls = []

    def popen(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return FakeProcess()

    answers = iter([False, True])
    monkeypatch.setattr(background, "_alive", lambda pid: pid == 4242)
    state = background.start("127.0.0.1", 8123, popen=popen, health=lambda url: next(answers), wait=2)

    [(cmd, kwargs)] = calls
    assert cmd[:3] == [sys.executable, "-m", "sololicense.cli"]
    assert cmd[3:] == ["serve", "--host", "127.0.0.1", "--port", "8123"]
    if os.name == "nt":
        flags = kwargs["creationflags"]
        assert flags & subprocess.CREATE_NEW_PROCESS_GROUP and flags & subprocess.DETACHED_PROCESS
    else:
        assert kwargs["start_new_session"] is True
    assert kwargs["stdin"] == subprocess.DEVNULL
    assert state["status"] == "started" and state["pid"] == 4242
    saved = json.loads((solo_home / "gate.pid").read_text())
    assert saved["pid"] == 4242 and saved["url"] == "http://127.0.0.1:8123"
    assert (solo_home / "gate.log").exists()


def test_start_twice_does_not_spawn_a_second_gate(solo_home, monkeypatch):
    solo_home.mkdir(parents=True)
    (solo_home / "gate.pid").write_text(json.dumps({"pid": 4242, "url": "http://127.0.0.1:8000", "port": 8000}))
    monkeypatch.setattr(background, "_alive", lambda pid: True)

    def popen(*a, **k):
        raise AssertionError("must not spawn")

    state = background.start("127.0.0.1", 8000, popen=popen, health=lambda url: True)
    assert state["status"] == "running"


def test_start_reports_a_gate_that_is_already_serving(solo_home):
    def popen(*a, **k):
        raise AssertionError("must not spawn")

    state = background.start("127.0.0.1", 8000, popen=popen, health=lambda url: True)
    assert state["status"] == "external"


def test_status_and_stop_with_nothing_running(solo_home, monkeypatch, capsys):
    monkeypatch.setattr(background, "healthy", lambda url, timeout=2.0: False)
    assert cli.main(["status"]) == 1
    assert "not running" in capsys.readouterr().out
    assert cli.main(["stop"]) == 0


def test_stop_clears_a_stale_pidfile(solo_home, monkeypatch):
    solo_home.mkdir(parents=True)
    (solo_home / "gate.pid").write_text(json.dumps({"pid": 999999, "url": "http://127.0.0.1:8000", "port": 8000}))
    monkeypatch.setattr(background, "_alive", lambda pid: False)
    monkeypatch.setattr(background, "healthy", lambda url, timeout=2.0: False)
    result = background.stop()
    assert result["status"] == "stale"
    assert not (solo_home / "gate.pid").exists()


def test_the_port_comes_from_the_configured_gate_url(monkeypatch):
    monkeypatch.delenv("SOLO_LICENSE_PORT", raising=False)
    monkeypatch.setenv("SOLO_LICENSE_URL", "http://127.0.0.1:8765")
    assert background.default_port() == 8765
    monkeypatch.setenv("SOLO_LICENSE_PORT", "9001")
    assert background.default_port() == 9001


def test_alive_is_false_for_a_process_that_does_not_exist():
    assert background._alive(os.getpid())
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()
    assert not background._alive(proc.pid)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_a_real_background_gate_starts_answers_and_stops(tmp_path, monkeypatch):
    pytest.importorskip("uvicorn")
    monkeypatch.setenv("SOLO_LICENSE_HOME", str(tmp_path / "solo"))
    for var in ("SOLO_LICENSE_DB", "SOLO_LEDGER_REPO"):
        monkeypatch.delenv(var, raising=False)
    port = _free_port()
    state = background.start("127.0.0.1", port, wait=60)
    try:
        assert state["status"] == "started", (tmp_path / "solo" / "gate.log").read_text(errors="ignore")
        assert background.healthy(f"http://127.0.0.1:{port}")
        assert background.status()["healthy"] is True
    finally:
        stopped = background.stop()
    assert stopped["status"] == "stopped"
    assert not background._alive(state["pid"])
    assert not (tmp_path / "solo" / "gate.pid").exists()
