"""Run the gate detached: ``solo-license serve --background``, ``stop`` and ``status``.

The gate is the same ``solo-license serve`` process, started without a
console and in its own process group / session so closing the terminal does
not stop it. Its pid and URL go to ``~/.solo-license/gate.pid`` and its
output to ``~/.solo-license/gate.log``. Standard library only.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from sololicense.coding.global_install import solo_home

HEALTH_PATH = "/api/coding/agents"


def pidfile() -> Path:
    return solo_home() / "gate.pid"


def logfile() -> Path:
    return solo_home() / "gate.log"


def default_port() -> int:
    """``SOLO_LICENSE_PORT``, else the port of ``SOLO_LICENSE_URL`` (what the hooks call), else 8000."""
    if os.environ.get("SOLO_LICENSE_PORT", "").strip().isdigit():
        return int(os.environ["SOLO_LICENSE_PORT"])
    return urlparse(os.environ.get("SOLO_LICENSE_URL", "http://127.0.0.1:8000")).port or 8000


def _url(host: str, port: int) -> str:
    return f"http://{'127.0.0.1' if host in ('0.0.0.0', '::', '') else host}:{port}"


def healthy(url: str, timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(url.rstrip("/") + HEALTH_PATH, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


def _alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        # os.kill(pid, 0) would terminate the process on Windows.
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(0x1000, False, pid)   # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            return bool(kernel32.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == 259  # STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def read_state() -> dict | None:
    try:
        state = json.loads(pidfile().read_text(encoding="utf-8"))
        return state if isinstance(state, dict) and isinstance(state.get("pid"), int) else None
    except (OSError, ValueError):
        return None


def _detach_kwargs() -> dict:
    if os.name == "nt":
        return {"creationflags": subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def start(host: str = "127.0.0.1", port: int | None = None, *, wait: float = 30.0,
          popen=subprocess.Popen, health=healthy) -> dict:
    """Start the gate in the background unless it already answers."""
    port = port or default_port()
    url = _url(host, port)
    state = read_state()
    if state and _alive(state["pid"]):
        return {"status": "running", **state}
    if health(url):
        return {"status": "external", "url": url}
    home = solo_home()
    home.mkdir(parents=True, exist_ok=True)
    log = logfile()
    # The child runs from the user dir, so make this very package importable there too.
    package_root = str(Path(__file__).resolve().parent.parent)
    pythonpath = os.pathsep.join(p for p in (package_root, os.environ.get("PYTHONPATH", "")) if p)
    with open(log, "ab") as out:
        out.write(f"\n--- {datetime.now(timezone.utc).isoformat()} solo-license serve on {url}\n".encode())
        out.flush()
        process = popen(
            [sys.executable, "-m", "sololicense.cli", "serve", "--host", host, "--port", str(port)],
            stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT, cwd=str(home), close_fds=True,
            env={**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONPATH": pythonpath}, **_detach_kwargs(),
        )
    state = {"pid": process.pid, "host": host, "port": port, "url": url, "log": str(log),
             "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    pidfile().write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    deadline = time.monotonic() + wait
    while time.monotonic() < deadline:
        if health(url):
            return {"status": "started", **state}
        if process.poll() is not None:
            pidfile().unlink(missing_ok=True)
            return {"status": "failed", **state}
        time.sleep(0.25)
    return {"status": "starting", **state}


def _kill(pid: int) -> None:
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, check=False)
        return
    try:
        os.killpg(pid, signal.SIGTERM)       # the gate leads its own session
    except (ProcessLookupError, PermissionError):
        return
    for _ in range(40):
        if not _alive(pid):
            return
        time.sleep(0.25)
    try:
        os.killpg(pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


def stop() -> dict:
    state = read_state()
    if not state:
        url = _url("127.0.0.1", default_port())
        return {"status": "external" if healthy(url) else "not-running", "url": url}
    pid = state["pid"]
    if not _alive(pid):
        pidfile().unlink(missing_ok=True)
        return {"status": "stale", **state}
    _kill(pid)
    for _ in range(40):
        if not _alive(pid):
            break
        time.sleep(0.25)
    pidfile().unlink(missing_ok=True)
    return {"status": "stopped" if not _alive(pid) else "still-running", **state}


def status() -> dict:
    state = read_state()
    alive = bool(state and _alive(state["pid"]))
    url = (state or {}).get("url") or _url("127.0.0.1", default_port())
    return {**(state or {}), "url": url, "running": alive, "healthy": healthy(url), "log": str(logfile())}
