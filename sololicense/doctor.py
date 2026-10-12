"""``solo-license doctor``: is everything in place for the gate to see your agents?

Each check is pass / warn / fail (or info). Any fail makes ``doctor`` exit 1.
Standard library only: it runs before the server's dependencies are installed.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from sololicense.coding import global_install as gi
from sololicense.coding.agents import AGENTS, AgentSpec
from sololicense.coding.install import DEFAULT_URL, MARK, SHIM_SOURCE

# Agent CLIs worth reporting, by executable name; none is required.
AGENT_CLIS = ("claude", "codex", "cursor-agent", "gemini", "copilot", "grok", "kiro-cli", "opencode")


@dataclass(frozen=True)
class Check:
    level: str      # pass | warn | fail | info
    label: str
    detail: str


def _version(exe: str) -> str:
    try:
        result = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=15,
                                stdin=subprocess.DEVNULL, check=False)
    except (OSError, subprocess.SubprocessError):
        return ""
    lines = (result.stdout or result.stderr or "").strip().splitlines()
    return lines[0].strip()[:80] if lines else ""


def _read(path: Path) -> str:
    if path.is_dir():
        return "".join(p.read_text(encoding="utf-8", errors="ignore") for p in sorted(path.glob("*")) if p.is_file())
    return path.read_text(encoding="utf-8", errors="ignore") if path.is_file() else ""


def _strings(value) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        value = list(value.values())
    return [s for v in value for s in _strings(v)] if isinstance(value, list) else []


def _commands(path: Path) -> str:
    """The text a shell would see: JSON string values decoded, other files as they are."""
    text = _read(path)
    if path.suffix == ".json":
        try:
            return "\n".join(_strings(json.loads(text)))
        except ValueError:
            pass
    return text


def _wired(path: Path) -> bool:
    text = _read(path)
    return MARK in text or "/api/hooks/" in text


_SHIM_PATHS = (r'"([^"]+?hook\.py)"', r"'([^']+?hook\.py)'", r'(?:^|\s)([^\s"\']+hook\.py)(?=\s|$)')


def _inspect(spec: AgentSpec, path: Path, scope: str, url: str) -> tuple[str, str]:
    text = _commands(path)
    again = "solo-license init --global" if scope == "global" else f"solo-license init --agent {spec.key}"
    if spec.transport in ("http", "plugin"):
        pattern = r'\?\? "(https?://[^"]+)"' if spec.transport == "plugin" else r'(https?://[^\s"\'`]+?)/api/hooks/'
        urls = sorted(set(re.findall(pattern, text)))
        if urls != [url]:
            return "fail", f"{path} calls {', '.join(urls) or 'no gate'}, not {url}; run: {again} --url {url}"
        return "pass", f"{path} -> {url}"
    shims = sorted({p for rx in _SHIM_PATHS for p in re.findall(rx, text, flags=re.M)})
    if not shims:
        return "warn", f"{path}: no hook.py command found in it; run: {again}"
    missing = [s for s in shims if not Path(s).is_file()]
    if missing:
        return "fail", f"{path} runs {missing[0]}, which is missing; run: {again}"
    source = SHIM_SOURCE.read_text(encoding="utf-8")
    if any(Path(s).read_text(encoding="utf-8", errors="ignore") != source for s in shims):
        return "warn", f"{shims[0]} is older than this solo-license; run: {again}"
    shim_url = os.environ.get("SOLO_LICENSE_URL", DEFAULT_URL).rstrip("/")
    if shim_url != url:
        return "warn", f"{path}: the shim calls {shim_url} (SOLO_LICENSE_URL), not {url}"
    return "pass", f"{path} -> {shims[0]}"


def hook_checks(repo: Path, url: str) -> list[Check]:
    checks: list[Check] = []
    for key, spec in AGENTS.items():
        places = [("repo", repo / spec.config_path), ("global", gi.global_path(key))]
        wired = [(scope, path) for scope, path in places if _wired(path)]
        for scope, path in wired:
            level, detail = _inspect(spec, path, scope, url)
            if level == "pass" and scope == "global" and len(wired) == 2:
                level, detail = "warn", (f"{path}: also wired in this repo, so every event is gated twice; "
                                         f"remove one: solo-license init --global --remove --agent {key}")
            checks.append(Check(level, f"{spec.label} ({scope})", detail))
    if not checks:
        checks.append(Check("fail", "hooks", "No Solo License hooks in this repo or at user level; "
                                             "run: solo-license init --global"))
    return checks


def _neatlogs_saved() -> bool:
    db = Path(os.environ.get("SOLO_LICENSE_DB") or gi.solo_home() / "solo_license.db")
    if not db.is_file():
        return False
    try:
        conn = sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True)
        try:
            row = conn.execute("SELECT value FROM settings WHERE key = 'neatlogs_api_key'").fetchone()
        finally:
            conn.close()
    except sqlite3.Error:
        return False
    return bool(row and str(row[0]).strip())


def run(repo: Path, url: str, *, get: Callable[[str], dict | None],
        which: Callable[[str], str | None] | None = None,
        version: Callable[[str], str] | None = None) -> list[Check]:
    from sololicense import background

    which, version = which or shutil.which, version or _version
    url = url.rstrip("/")
    checks: list[Check] = []
    state = background.read_state()
    if get(f"{url}/api/coding/agents"):
        how = f" (background pid {state['pid']}, log {state.get('log')})" if state else ""
        checks.append(Check("pass", "gate", f"up at {url}{how}"))
        for seen in (get(f"{url}/api/coding") or {}).get("agents", []):
            checks.append(Check("info", f"seen {seen['agent']}",
                                f"{seen['decisions']} decisions, last {seen['last_seen']}"))
    else:
        checks.append(Check("fail", "gate", f"not reachable at {url}; start it: solo-license serve --background"))

    checks += hook_checks(repo, url)

    for exe in AGENT_CLIS:
        found = which(exe)
        checks.append(Check("pass", exe, f"{version(found) or 'found'} ({found})") if found
                      else Check("info", exe, "not found on PATH"))
    entire = which("entire")
    checks.append(Check("pass", "entire", f"{version(entire) or 'found'} ({entire})") if entire else
                  Check("warn", "entire", "Entire CLI not on PATH (optional): failed turns will not link to "
                                          "the session's checkpoints"))

    if os.environ.get("NEATLOGS_API_KEY", "").strip() or _neatlogs_saved():
        checks.append(Check("pass", "neatlogs", "API key configured"))
    else:
        checks.append(Check("warn", "neatlogs", "no API key (optional): traces stay in the local mirror; "
                                                "add one in the dashboard's settings or set NEATLOGS_API_KEY"))
    return checks


def exit_code(checks: list[Check]) -> int:
    return 1 if any(c.level == "fail" for c in checks) else 0


def render(checks: list[Check]) -> str:
    tags = {"pass": "PASS", "warn": "WARN", "fail": "FAIL", "info": "  - "}
    return "\n".join(f"{tags[c.level]}  {c.label:<30} {c.detail}" for c in checks)
