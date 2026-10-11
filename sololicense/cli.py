"""``solo-license``: install, run and check Solo License from one command.

    uvx --from git+https://github.com/JAYATIAHUJA/Solo_license solo-license init --agent auto
    solo-license serve            # the local gate + dashboard on http://127.0.0.1:8000
    solo-license doctor           # is the gate up, which agents are wired here
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

    install.main([str(args.repo), "--agent", args.agent, "--url", args.url])
    print("\nNext: run `solo-license serve` and keep it running, then `solo-license doctor`.")
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    from sololicense.coding.agents import AGENTS

    repo = Path(args.repo).resolve()
    ok = True
    health = _get(f"{args.url}/api/coding/agents")
    print(f"gate     {'up' if health else 'NOT REACHABLE'} at {args.url}")
    if not health:
        ok = False
        print("         start it with: solo-license serve")
    print(f"repo     {repo}")
    for spec in AGENTS.values():
        path = repo / spec.config_path
        wired = path.exists() and ("solo-license" in _read(path) or "/api/hooks/" in _read(path))
        if wired:
            print(f"  wired  {spec.label:<34} {spec.config_path}")
    shim = repo / ".solo-license" / "hook.py"
    if shim.exists():
        print(f"shim     {shim}")
    if health:
        seen = _get(f"{args.url}/api/coding") or {}
        for a in seen.get("agents", []):
            print(f"seen     {a['agent']}: {a['decisions']} decisions, last {a['last_seen']}")
    return 0 if ok else 1


def _read(path: Path) -> str:
    if path.is_dir():
        return "".join(p.read_text(encoding="utf-8", errors="ignore") for p in path.glob("*") if p.is_file())
    return path.read_text(encoding="utf-8", errors="ignore")


def cmd_prompt(args: argparse.Namespace) -> int:
    print(agent_prompt(args.agent))
    return 0


def cmd_hook(args: argparse.Namespace) -> int:
    from sololicense.coding import shim

    return shim.main(["hook", args.agent, args.event])


def cmd_serve(args: argparse.Namespace) -> int:
    try:
        import uvicorn  # noqa: F401
    except ImportError:
        print("The server needs its dependencies: uv tool install git+" + REPO_URL)
        return 1
    home = Path(os.environ.get("SOLO_LICENSE_HOME", Path.home() / ".solo-license"))
    home.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("SOLO_LICENSE_DB", str(home / "solo_license.db"))
    os.environ.setdefault("SOLO_LEDGER_REPO", str(home / "ledger"))
    os.environ.setdefault("SOLO_DEMO_MODE", "1")
    import uvicorn

    print(f"Solo License gate on http://{args.host}:{args.port}  (data in {home})")
    uvicorn.run("sololicense.api.app:app", host=args.host, port=args.port)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="solo-license", description="Earned autonomy for coding agents.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("init", help="wire the hooks for a coding agent into this repository")
    p.add_argument("--agent", default="auto", help="claude-code, codex, cursor, gemini, antigravity, copilot, "
                                                   "grok, windsurf, kiro, cline, opencode, auto or all")
    p.add_argument("--repo", default=".")
    p.add_argument("--url", default=DEFAULT_URL)
    p.set_defaults(fn=cmd_init)

    p = sub.add_parser("serve", help="run the local gate and dashboard")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    p.set_defaults(fn=cmd_serve)

    p = sub.add_parser("doctor", help="check the gate and this repository's hooks")
    p.add_argument("--repo", default=".")
    p.add_argument("--url", default=DEFAULT_URL)
    p.set_defaults(fn=cmd_doctor)

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
