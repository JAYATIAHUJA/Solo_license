"""``solo-license onboard``: from nothing to a gated agent in one command.

1. find the coding agents used here (Claude Code, Codex, Cursor, OpenCode, ...)
2. show the hook changes, then write them
3. make this machine's admin token and settings key (Keychain or a 0600 file)
4. start the gate in the background with them
5. check the gate answers a hook, with a harmless read
6. open the dashboard already signed in, at the setup guide, where neatlogs,
   Jev and Entire are optional steps
"""

from __future__ import annotations

import json
import shutil
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path
from typing import Callable

STEPS = 6


def _say(n: int, text: str) -> None:
    print(f"[{n}/{STEPS}] {text}")


def _confirm(question: str, assume_yes: bool) -> bool:
    if assume_yes or not sys.stdin.isatty():
        return True
    answer = input(f"{question} [Y/n] ").strip().lower()
    return answer in ("", "y", "yes")


def _post(url: str, body: dict, timeout: float = 10.0) -> dict | None:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.load(resp)
    except Exception:
        return None


def verify_gate(url: str, repo: Path, post: Callable[[str, dict], dict | None] = _post) -> tuple[bool, str]:
    """Send one harmless read through the same hook route Claude Code uses."""
    session = f"solo-license-onboard-{int(time.time())}"
    event = {"session_id": session, "cwd": str(repo), "hook_event_name": "PreToolUse",
             "tool_name": "Read", "tool_input": {"file_path": str(repo / "README.md")}}
    answer = post(f"{url}/api/hooks/pre-tool", event)
    if answer is None:
        return False, f"no answer from {url}/api/hooks/pre-tool"
    decision = ((answer.get("hookSpecificOutput") or {}).get("permissionDecision")) or "defer to the agent"
    return True, f"the gate answered a read in {repo.name}: {decision}"


def _get_as(url: str, token: str) -> dict | None:
    req = urllib.request.Request(url, headers={"authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.load(resp)
    except Exception:
        return None


def dashboard_url(url: str, get: Callable[[str], dict | None]) -> tuple[str, bool]:
    """The gate's own dashboard if it was built, else the dev server."""
    try:
        with urllib.request.urlopen(f"{url}/access", timeout=3) as resp:
            if b"<div id=\"root\"" in resp.read(4096):
                return url, True
    except Exception:
        pass
    return "http://127.0.0.1:5174", False


def integrations(settings: dict | None) -> list[str]:
    settings = settings or {}
    entire = shutil.which("entire")
    return [
        f"neatlogs (traces of every turn): {'connected' if settings.get('neatlogs_enabled') else 'optional - add NEATLOGS_API_KEY in the setup guide, step 3'}",
        f"Jev (calibrated judgements): {'connected' if settings.get('jev_enabled') else 'optional - built-in rules decide until you add TYPESAFE_API_KEY'}",
        f"Entire (checkpoints of failed turns): {'found at ' + entire if entire else 'optional - install the Entire CLI to link failed turns to checkpoints'}",
    ]


def run(args, *, get: Callable[[str], dict | None]) -> int:
    from sololicense import background, credentials
    from sololicense.coding import install
    from sololicense.coding.agents import resolve

    repo = Path(args.repo).resolve()
    url = args.url.rstrip("/")

    found = install.detect(repo)
    agents = (found or ["claude-code"]) if args.agent == "auto" else [args.agent]
    labels = ", ".join(resolve(a).label for a in agents)
    _say(1, f"Agents: {labels}" + ("" if found or args.agent != "auto" else " (none found; Claude Code by default)"))

    changes = [c for a in agents for c in install.plan(repo, url, a)]
    if any(resolve(a).transport == "command" for a in agents):
        changes = install.shim_changes(install._repo_hook(repo)) + changes
    _say(2, f"Hooks for {repo}:")
    print(install.diff(changes) or "  already installed, nothing to change")
    if changes and not _confirm("Write these hook changes?", args.yes):
        print("Stopped; nothing was written.")
        return 1
    for a in agents:
        install.install(repo, url, resolve(a).key)

    creds, where = credentials.ensure()
    credentials.apply_env(creds)
    _say(3, f"Local admin '{creds['admin_id']}' and settings key kept in {where}")

    port = background.default_port()
    state = background.start("127.0.0.1", port)
    if state["status"] == "failed":
        print(f"The gate exited at once; see {state['log']}")
        return 1
    if state["status"] == "external":
        _say(4, f"A gate already answers at {state['url']} (started elsewhere); using it. "
                "Restart it with `solo-license stop` + `solo-license serve --background` to load the new admin key.")
    else:
        _say(4, f"Gate running at {state['url']} (pid {state.get('pid')}); log {state.get('log')}")

    ok, how = verify_gate(url, repo)
    _say(5, ("OK: " if ok else "Not yet: ") + how)

    web, served = dashboard_url(url, get)
    link = f"{web}/access?next=%2Fonboarding#token={creds['admin_token']}"
    _say(6, "Dashboard: " + (f"{web}/onboarding" if served else
                             f"{web}/onboarding (start it with: npm --prefix frontend run dev; "
                             "or build it once with npm --prefix frontend run build and the gate serves it)"))
    dashboard = _get_as(f"{url}/api/dashboard", creds["admin_token"])
    for line in integrations((dashboard or {}).get("settings")):
        print(f"      - {line}")
    if not args.no_browser:
        webbrowser.open(link)
        print("      Opened your browser, signed in as the local admin.")
    else:
        print(f"      Sign-in link (keep it private): {link}")
    print("\nNow open your agent in this repository and ask it to run the tests. "
          "`solo-license doctor` checks the wiring, `solo-license budget` shows spend.")
    return 0 if ok else 1
