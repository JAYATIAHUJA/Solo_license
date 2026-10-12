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


def _start_gate(start) -> tuple[str, dict]:
    from sololicense import background

    port = background.default_port()
    for _ in range(8):
        state = start("127.0.0.1", port)
        if state["status"] != "failed":
            return f"http://127.0.0.1:{port}", state
        port += 1
    return f"http://127.0.0.1:{port - 1}", state


def run(args, *, get: Callable[[str], dict | None]) -> int:
    from sololicense import background, credentials
    from sololicense.coding import install
    from sololicense.coding.agents import resolve

    repo = Path(args.repo).resolve()
    url = args.url.rstrip("/")

    found = install.detect(repo)
    labels = ", ".join(resolve(a).label for a in found) if found else "none found"
    _say(1, f"Agents on this machine: {labels}")

    creds, where = credentials.ensure()
    credentials.apply_env(creds)
    _say(2, f"Local admin '{creds['admin_id']}' and settings key kept in {where}")

    url, state = _start_gate(background.start)
    if state["status"] == "failed":
        print(f"The gate would not start; see {state['log']}")
        return 1
    if state["status"] == "external":
        _say(3, f"A gate already answers at {state['url']} (started elsewhere); using it. "
                "Restart it with `solo-license stop` + `solo-license serve --background` to load the new admin key.")
    else:
        _say(3, f"Gate running at {state['url']} (pid {state.get('pid')}); log {state.get('log')}")

    ok, how = verify_gate(url, repo)
    _say(4, ("OK: " if ok else "Not yet: ") + how)

    if getattr(args, "no_browser", False):
        # headless: install for every agent found, exactly as before
        agents = (found or ["claude-code"]) if args.agent == "auto" else [args.agent]
        for a in agents:
            install.install(repo, url, resolve(a).key)
        _say(5, f"Hooks written for {', '.join(resolve(a).label for a in agents)}")
        link = f"{url}/onboarding#token={creds['admin_token']}"
        print(f"      Sign-in link (keep it private): {link}")
        return 0 if ok else 1

    # the browser chooses: register the wizard, open it, and wait for the pick
    req = urllib.request.Request(
        f"{url}/api/wizard/start",
        data=json.dumps({"repo": str(repo), "url": url}).encode(),
        method="POST", headers={"content-type": "application/json",
                                "authorization": f"Bearer {creds['admin_token']}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            json.load(resp)
    except Exception:
        print("The gate did not accept the wizard setup; continuing headless.")
        return run_headless(args, repo, url, found, creds, ok)
    link = f"{url}/onboarding?wizard=1#token={creds['admin_token']}"
    webbrowser.open(link)
    _say(5, "Choose the agents (and connect neatlogs + Jev) in the browser that just opened.")
    print(f"      Waiting here: {link}")
    chosen: dict = {}
    deadline = time.time() + 900
    while time.time() < deadline:
        time.sleep(2)
        state_now = get(f"{url}/api/wizard")
        if state_now and state_now.get("status") == "installed":
            chosen = state_now
            break
    if not chosen:
        print("      No selection after 15 minutes; nothing was installed.")
        return 1
    names = ", ".join(resolve(a).label for a in chosen.get("installed", []))
    _say(5, f"Hooks written for: {names or 'nothing'}")
    for agent, error in (chosen.get("errors") or {}).items():
        print(f"      {agent}: {error}")
    ok2, how2 = verify_gate(url, repo)
    _say(6, ("OK: " if ok2 else "Not yet: ") + how2)
    print("\nNow open your agent in this repository and ask it to run the tests. "
          "`solo-license doctor` checks the wiring, `solo-license budget` shows spend.")
    return 0 if ok2 else 1


def run_headless(args, repo: Path, url: str, found, creds, ok: bool) -> int:
    from sololicense.coding import install
    from sololicense.coding.agents import resolve

    agents = (found or ["claude-code"]) if args.agent == "auto" else [args.agent]
    for a in agents:
        install.install(repo, url, resolve(a).key)
    print(f"      Hooks written for {', '.join(resolve(a).label for a in agents)}")
    print(f"      Sign-in link (keep it private): {url}/onboarding#token={creds['admin_token']}")
    return 0 if ok else 1
