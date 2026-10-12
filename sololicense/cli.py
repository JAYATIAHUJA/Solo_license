"""``solo-license``: install, run and check Solo License from one command.

    uvx --from git+https://github.com/JAYATIAHUJA/Solo_license solo-license init --agent auto
    solo-license onboard          # one command: hooks, local admin key, gate, browser, first check
    solo-license init --global    # user-level hooks: every repository on this machine
    solo-license serve            # the local gate + dashboard on http://127.0.0.1:8000
    solo-license serve --background / stop / status
    solo-license doctor           # is the gate up, which agents are wired here
    solo-license budget           # what the agents spent today, against the caps
    solo-license explain [turn]   # one turn's story: decisions, trace, Entire checkpoint, rewind
    solo-license prompt --agent codex   # a ready prompt that makes your agent set itself up
    solo-license hook <agent> <event>   # the command-hook shim (normally called by the agent)

``init``, ``doctor``, ``prompt`` and ``hook`` use only the standard library.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path

REPO_URL = "https://github.com/JAYATIAHUJA/Solo_license"
INSTALL_ONE_LINER = f"uvx --from git+{REPO_URL} solo-license init --agent auto"
GLOBAL_STEPS = (f"uv tool install git+{REPO_URL}", "solo-license init --global", "solo-license serve --background")
GLOBAL_ONE_LINER = " && ".join(GLOBAL_STEPS)
DEFAULT_URL = os.environ.get("SOLO_LICENSE_URL", "http://127.0.0.1:8000")


def agent_prompt(agent: str = "auto") -> str:
    """A prompt a user pastes into their coding agent so it installs Solo License itself."""
    target = "the coding agent you are" if agent == "auto" else agent
    return f"""Set up Solo License in this repository for {target}. Solo License answers your permission prompts from a track record you earn here, and checks each turn for over-editing and failing tests.

1. If `uv` is not installed, install it (macOS/Linux: `curl -LsSf https://astral.sh/uv/install.sh | sh`; Windows: `powershell -c "irm https://astral.sh/uv/install.ps1 | iex"`). Ask me before you run that.
2. Run: `uv tool install git+{REPO_URL}`
3. Run: `solo-license init --agent {agent}` in this repository's root. It only adds hook configuration for you and a `.solo-license/` folder; change nothing else.
4. Tell me to run `solo-license serve` in another terminal (it must keep running), then run `solo-license doctor` and show me its output.
5. Summarise which files were added. Do not commit them unless I ask."""


def _get(url: str, timeout: float = 3.0) -> dict | None:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return json.load(resp)
    except Exception:
        return None


def cmd_init(args: argparse.Namespace) -> int:
    from sololicense.coding import install

    if args.global_:
        return cmd_init_global(args)
    flags = (["--dry-run"] if args.dry_run else []) + (["--remove"] if args.remove else [])
    install.main([str(args.repo), "--agent", args.agent, "--url", args.url, *flags])
    if not (args.dry_run or args.remove):
        print("\nNext: run `solo-license serve` and keep it running, then `solo-license doctor`.")
    return 0


def cmd_onboard(args: argparse.Namespace) -> int:
    from sololicense import onboard

    return onboard.run(args, get=_get)


def cmd_init_global(args: argparse.Namespace) -> int:
    from sololicense.coding import global_install

    return global_install.run(args.agent, args.url, dry_run=args.dry_run, remove=args.remove)


def cmd_doctor(args: argparse.Namespace) -> int:
    from sololicense import doctor

    repo = Path(args.repo).resolve()
    print(f"repo  {repo}")
    checks = doctor.run(repo, args.url, get=_get)
    print(doctor.render(checks))
    return doctor.exit_code(checks)


def cmd_policy(args: argparse.Namespace) -> int:
    from sololicense.coding import policy

    path = policy.write_starter(Path(args.repo).resolve())
    print(f"Policy file: {path}\nEdit it, then commit it: privilege changes are reviewed like code.")
    return 0


def cmd_prompt(args: argparse.Namespace) -> int:
    print(agent_prompt(args.agent))
    return 0


def cmd_hook(args: argparse.Namespace) -> int:
    from sololicense.coding import shim

    return shim.main(["hook", args.agent, args.event])


def cmd_serve(args: argparse.Namespace) -> int:
    from sololicense import background

    try:
        import uvicorn  # noqa: F401
    except ImportError:
        print("The server needs its dependencies: uv tool install git+" + REPO_URL)
        return 1
    args.port = args.port or background.default_port()
    from sololicense import credentials

    credentials.apply_env()  # the admin token and settings key made by `solo-license onboard`, if any
    if args.background:
        return cmd_serve_background(args)
    home = Path(os.environ.get("SOLO_LICENSE_HOME", Path.home() / ".solo-license"))
    home.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("SOLO_LICENSE_DB", str(home / "solo_license.db"))
    os.environ.setdefault("SOLO_LEDGER_REPO", str(home / "ledger"))
    os.environ.setdefault("SOLO_DEMO_MODE", "1")
    import uvicorn

    print(f"Solo License gate on http://{args.host}:{args.port}  (data in {home})")
    uvicorn.run("sololicense.api.app:app", host=args.host, port=args.port)
    return 0


def cmd_serve_background(args: argparse.Namespace) -> int:
    from sololicense import background

    state = background.start(args.host, args.port)
    status = state["status"]
    if status == "external":
        print(f"Something already answers at {state['url']}; not starting another gate.")
        return 0
    if status == "failed":
        print(f"The gate exited at once; see {state['log']}")
        return 1
    print({"running": "Already running", "started": "Started", "starting": "Still starting"}[status]
          + f": Solo License gate on {state['url']} (pid {state['pid']})")
    print(f"Log: {state['log']}\nStop it with: solo-license stop")
    return 0


def cmd_stop(args: argparse.Namespace) -> int:
    from sololicense import background

    result = background.stop()
    print({"stopped": f"Stopped the gate (pid {result.get('pid')}).",
           "still-running": f"Could not stop pid {result.get('pid')}.",
           "stale": "The gate was not running (cleared a stale pid file).",
           "pid-reused": f"Pid {result.get('pid')} now belongs to another program; left it running "
                         "and cleared the pid file.",
           "not-running": "The gate is not running.",
           "external": f"A gate answers at {result['url']}, but it was not started with --background; "
                       "stop it where it runs."}[result["status"]])
    return 1 if result["status"] == "still-running" else 0


def cmd_status(args: argparse.Namespace) -> int:
    from sololicense import background

    state = background.status()
    if state["healthy"]:
        how = f"background pid {state['pid']}" if state["running"] else "started outside --background"
        print(f"Solo License gate is up at {state['url']} ({how})\nLog: {state['log']}")
        return 0
    if state["running"]:
        print(f"Gate process {state['pid']} is running but not answering at {state['url']} yet; "
              f"see {state['log']}")
        return 1
    print(f"The gate is not running at {state['url']}. Start it: solo-license serve --background")
    return 1


def _usd(value) -> str:
    return "no cap" if value is None else f"${float(value):,.2f}"


def budget_lines(data: dict) -> list[str]:
    """The Budget page as terminal lines."""
    lines = [f"Spend on {data.get('day', 'today')}"]
    repos = data.get("repos") or []
    if not repos:
        lines.append("  no repositories yet - spend appears once an agent works in a repo with Solo License")
    for r in repos:
        limits = r.get("limits") or {}
        cap = limits.get("day_usd")
        share = f" ({100 * r['day_usd'] / cap:.0f}%)" if cap else ""
        resumed = " | resumed by a person today" if r.get("resumed_today") else ""
        lines.append(f"  {r['repo']}: {_usd(r['day_usd'])} of {_usd(cap)} today{share}"
                     f" | per session {_usd(limits.get('session_usd'))}{resumed}")
    sessions = data.get("sessions") or []
    if sessions:
        lines.append("Recent sessions")
    for s in sessions:
        state = "STOPPED at the cap" if s.get("blocked") else {"warn": "near the cap"}.get(s.get("state"), "ok")
        model = f" ({s['model']})" if s.get("model") else ""
        how = "reported by the agent" if s.get("source") == "reported" else "estimated from tokens"
        lines.append(f"  {_usd(s['usd'])}  {s['agent']}{model} in {s['repo']} | {how} | {state}")
    saved = (data.get("savings") or {}).get("usd_saved")
    if saved is not None:
        lines.append(f"Developer time saved by earned autonomy: {_usd(saved)}")
    if any(s.get("blocked") for s in sessions):
        lines.append("A stopped session continues once you press Resume on the dashboard's Budget page.")
    return lines


def pick_turn(turns: list[dict]) -> dict | None:
    """The newest turn that went wrong, else the newest turn."""
    return next((t for t in turns if t.get("status") in ("failed", "blocked")), None) or (turns[0] if turns else None)


def explain_lines(story: dict) -> list[str]:
    """A turn's story for the terminal."""
    t = story["turn"]
    prompt = (t.get("prompt") or "turn without a prompt")[:140]
    lines = [f"Turn {t['id']} in {t['repo']} ({t.get('created_at', '')}): \"{prompt}\"",
             f"  status: {t.get('status')}"
             + (f" | {t['lines_changed']} lines in {t['files_changed']} files" if t.get("files_changed") is not None else "")
             + (f" | scope {t['scope_score']}/5" if t.get("scope_score") is not None else "")
             + (f" | tests {t['tests']}" if t.get("tests") and t["tests"] != "none" else "")]
    if t.get("reason"):
        lines.append("  why: " + t["reason"].splitlines()[0][:200])
    decisions = story.get("decisions") or []
    if decisions:
        lines.append("Decisions")
    for d in decisions:
        lines.append(f"  {d['decision']:<5} {d['command'][:70]} | {d['action_class']} at L{d['level']} | "
                     f"{d.get('decided_by', '')} | {d.get('outcome', '')}")
    for r in story.get("told") or []:
        lines.append("Agent was told: " + (r.get("text") or "").removeprefix("Solo License: ").splitlines()[0][:200])
    for e in story.get("events") or []:
        lines.append(f"License: {e['action_class']} {e['kind']} L{e['from_level']} -> L{e['to_level']}"
                     + (f" | ledger commit {e['git_sha'][:7]}" if e.get("git_sha") else ""))
    spans = story.get("spans") or []
    trace = t.get("trace_id")
    if t.get("neatlogs_link"):
        lines.append(f"neatlogs trace: {t['neatlogs_link']}")
    elif trace:
        lines.append(f"Trace {trace} (local only; add NEATLOGS_API_KEY to send traces to neatlogs)")
    if spans:
        lines.append("  " + " -> ".join(s["name"] + ("!" if s["status"] == "error" else "") for s in spans[:14])
                     + (" ..." if len(spans) > 14 else ""))
    entire = story.get("entire") or {}
    lines.append(f"Entire checkpoint: {entire['explain']}" if entire.get("checkpoint")
                 else "Entire checkpoint: none linked (install the Entire CLI in the repo: entire enable)")
    rewind = story.get("rewind") or {}
    if rewind.get("available"):
        lines.append("Rewind: " + rewind["how"])
    return lines


def cmd_explain(args: argparse.Namespace) -> int:
    base = args.url.rstrip("/")
    turn_id = args.turn
    if turn_id is None:
        data = _get(f"{base}/api/coding")
        if data is None:
            print(f"The gate is not answering at {args.url}. Start it: solo-license serve --background")
            return 1
        turns = data.get("turns") or []
        if args.list:
            for t in turns[:15]:
                print(f"  {t['id']:>5}  {t['status']:<9} {t['repo']:<20} {(t.get('prompt') or '')[:60]}")
            return 0
        chosen = pick_turn(turns)
        if chosen is None:
            print("No turns yet. Ask your agent for something in a repository with Solo License installed.")
            return 0
        turn_id = chosen["id"]
    story = _get(f"{base}/api/coding/turns/{turn_id}/explain")
    if story is None:
        print(f"No turn {turn_id}, or the gate is not answering at {args.url}.")
        return 1
    print("\n".join(explain_lines(story)))
    return 0


def cmd_budget(args: argparse.Namespace) -> int:
    data = _get(f"{args.url.rstrip('/')}/api/coding/budget")
    if data is None:
        print(f"The gate is not answering at {args.url}. Start it: solo-license serve --background")
        return 1
    print("\n".join(budget_lines(data)))
    return 0


def _add_init_scope_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--global", dest="global_", action="store_true",
                   help="user-level hooks for every repository (with --agent auto: the agents found in your home)")
    p.add_argument("--dry-run", action="store_true", help="print the changes as a diff; write nothing")
    p.add_argument("--remove", action="store_true", help="take Solo License's hooks out again (uninstall)")


def _add_background_commands(sub) -> None:
    p = sub.add_parser("stop", help="stop the gate started with serve --background")
    p.set_defaults(fn=cmd_stop)
    p = sub.add_parser("status", help="is the gate running, and where")
    p.set_defaults(fn=cmd_status)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="solo-license", description="Earned autonomy for coding agents.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("init", help="wire the hooks for a coding agent into this repository")
    p.add_argument("--agent", default="auto", help="claude-code, codex, cursor, gemini, antigravity, copilot, "
                                                   "grok, windsurf, kiro, cline, opencode, auto or all")
    p.add_argument("--repo", default=".")
    p.add_argument("--url", default=DEFAULT_URL)
    _add_init_scope_args(p)
    p.set_defaults(fn=cmd_init)

    p = sub.add_parser("onboard", help="one command: detect agents, install hooks, make a local admin, "
                                         "start the gate, open the dashboard")
    p.add_argument("--agent", default="auto")
    p.add_argument("--repo", default=".")
    p.add_argument("--url", default=DEFAULT_URL)
    p.add_argument("--yes", "-y", action="store_true", help="write the hooks without asking")
    p.add_argument("--no-browser", action="store_true", help="print the sign-in link instead of opening it")
    p.set_defaults(fn=cmd_onboard)

    p = sub.add_parser("serve", help="run the local gate and dashboard")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=None, help="default: the port of SOLO_LICENSE_URL, else 8000")
    p.add_argument("--background", action="store_true", help="detach; pid and log under ~/.solo-license")
    p.set_defaults(fn=cmd_serve)
    _add_background_commands(sub)

    p = sub.add_parser("doctor", help="check the gate and this repository's hooks")
    p.add_argument("--repo", default=".")
    p.add_argument("--url", default=DEFAULT_URL)
    p.set_defaults(fn=cmd_doctor)

    p = sub.add_parser("budget", help="what the coding agents spent today, against the caps")
    p.add_argument("--url", default=DEFAULT_URL)
    p.set_defaults(fn=cmd_budget)

    p = sub.add_parser("explain", help="one turn's story: decisions, trace, Entire checkpoint, how to rewind")
    p.add_argument("turn", type=int, nargs="?", default=None, help="turn id (default: the newest failed turn)")
    p.add_argument("--list", action="store_true", help="list recent turns with their ids")
    p.add_argument("--url", default=DEFAULT_URL)
    p.set_defaults(fn=cmd_explain)

    p = sub.add_parser("policy", help="write a starter .solo-license/policy.toml for this repository")
    p.add_argument("action", choices=["init"])
    p.add_argument("--repo", default=".")
    p.set_defaults(fn=cmd_policy)

    p = sub.add_parser("prompt", help="print a prompt that makes your agent install Solo License")
    p.add_argument("--agent", default="auto")
    p.set_defaults(fn=cmd_prompt)

    p = sub.add_parser("hook", help="command-hook shim (called by the agent)")
    p.add_argument("agent")
    p.add_argument("event")
    p.set_defaults(fn=cmd_hook)

    args = parser.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
