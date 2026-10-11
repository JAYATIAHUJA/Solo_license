"""Install Solo License's hooks for a coding agent in one repository.

    solo-license init --agent codex            # or: python -m sololicense.coding.install . --agent codex

Writes that agent's own hook configuration (merged with whatever is already
there, such as Entire's hooks) and, for agents whose hooks run commands, a
one-file shim at ``.solo-license/hook.py``. Running it twice changes nothing.
Standard library only.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import stat
import sys
from pathlib import Path

from sololicense.coding.agents import AGENTS, AgentSpec, resolve

DEFAULT_URL = "http://127.0.0.1:8000"
SHIM_SOURCE = Path(__file__).with_name("shim.py")
MARK = "solo-license"   # how our entries are recognised on re-install


# --- shared helpers -------------------------------------------------------------

def _load(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8") or "{}")
        except ValueError:
            raise SystemExit(f"{path} is not valid JSON; fix or remove it first.")
    return {}


def _save(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _ours(entry) -> bool:
    return MARK in json.dumps(entry) or "/api/hooks/" in json.dumps(entry)


def _merge(existing: dict, ours: dict) -> dict:
    """Event -> list merge that replaces only our previous entries."""
    for event, entries in ours.items():
        kept = [e for e in existing.get(event, []) if not _ours(e)]
        existing[event] = kept + entries
    return existing


def _shim(repo: Path) -> Path:
    target = repo / ".solo-license" / "hook.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(SHIM_SOURCE, target)
    (repo / ".solo-license" / ".gitignore").write_text("*\n", encoding="utf-8")
    return target


# Hook commands are run by the agent through a shell. Inside double quotes a
# POSIX shell still expands $(...), `...` and $VAR, and cmd.exe expands %VAR%,
# so a path holding any of these is refused rather than written into a command.
_UNSAFE_PATH_CHARS = set('$`"\'!%;&|<>\n\r')
_SAFE_URL = re.compile(r"^https?://[A-Za-z0-9.\-]+(:\d{1,5})?(/[A-Za-z0-9._~/-]*)?$")


def _safe_path(path: str, what: str) -> str:
    bad = sorted(set(path) & _UNSAFE_PATH_CHARS)
    if bad:
        raise SystemExit(
            f"Refusing to write a hook command: the {what} path contains shell characters {bad!r}: {path}\n"
            "Move the repository (or Python) to a path without them and run init again."
        )
    return path


def validate_url(url: str) -> str:
    """The gate URL is written into configs and a TypeScript plugin: plain
    http(s)://host[:port][/path] only."""
    url = url.strip().rstrip("/")
    if not _SAFE_URL.match(url):
        raise SystemExit(f"Not a plain http(s) URL for the gate: {url!r} (expected e.g. http://127.0.0.1:8000)")
    return url


def _paths(repo: Path) -> tuple[str, str]:
    python = _safe_path(str(sys.executable), "Python")
    hook = _safe_path(str(repo / ".solo-license" / "hook.py"), "repository")
    return python, hook


def _command(repo: Path, agent: str, event: str) -> str:
    """``"<python>" "<repo>/.solo-license/hook.py" <agent> <event>``. Paths are
    double-quoted for spaces (accepted by sh, bash, PowerShell and cmd) and
    checked to hold nothing a shell would expand. The trailing comment marks
    the entry as ours so a re-install replaces it."""
    python, hook = _paths(repo)
    return '"' + python + '" "' + hook + '" ' + agent + " " + event + " # " + MARK


# --- per agent ------------------------------------------------------------------

def _claude(repo: Path, url: str) -> Path:
    def http(event: str, timeout: int = 10) -> dict:
        return {"type": "http", "url": f"{url}/api/hooks/{event}", "timeout": timeout,
                "headers": {"X-Solo-Hook-Key": "$SOLO_HOOK_KEY"}, "allowedEnvVars": ["SOLO_HOOK_KEY"]}

    ours = {
        "UserPromptSubmit": [{"hooks": [http("user-prompt")]}],
        "PermissionRequest": [{"matcher": "*", "hooks": [http("permission")]}],
        "PostToolUse": [{"matcher": "*", "hooks": [http("post-tool")]}],
        "PostToolUseFailure": [{"matcher": "*", "hooks": [http("post-tool-failure")]}],
        "Stop": [{"hooks": [http("stop", 150)]}],
    }
    path = repo / ".claude" / "settings.local.json"
    data = _load(path)
    data["hooks"] = _merge(data.get("hooks", {}), ours)
    _save(path, data)
    return path


def _codex(repo: Path, url: str) -> Path:
    cmd = lambda e, t=30: {"type": "command", "command": _command(repo, "codex", e), "timeout": t}  # noqa: E731
    ours = {
        "UserPromptSubmit": [{"hooks": [cmd("UserPromptSubmit")]}],
        "PermissionRequest": [{"matcher": "*", "hooks": [cmd("PermissionRequest")]}],
        "PostToolUse": [{"matcher": "*", "hooks": [cmd("PostToolUse")]}],
        "Stop": [{"hooks": [cmd("Stop", 150)]}],
    }
    path = repo / ".codex" / "hooks.json"
    data = _load(path)
    data["hooks"] = _merge(data.get("hooks", {}), ours)
    _save(path, data)
    return path


def _cursor(repo: Path, url: str) -> Path:
    cmd = lambda e, **kw: {"command": _command(repo, "cursor", e), **kw}  # noqa: E731
    ours = {
        "beforeSubmitPrompt": [cmd("beforeSubmitPrompt")],
        "beforeShellExecution": [cmd("beforeShellExecution")],
        "preToolUse": [cmd("preToolUse", matcher="Write|Delete")],
        "afterShellExecution": [cmd("afterShellExecution")],
        "afterFileEdit": [cmd("afterFileEdit")],
        "stop": [cmd("stop")],
    }
    path = repo / ".cursor" / "hooks.json"
    data = _load(path)
    data.setdefault("version", 1)
    data["hooks"] = _merge(data.get("hooks", {}), ours)
    _save(path, data)
    return path


def _gemini(repo: Path, url: str) -> Path:
    cmd = lambda e, t=30000: {"name": MARK, "type": "command", "command": _command(repo, "gemini", e), "timeout": t}  # noqa: E731
    ours = {
        "BeforeAgent": [{"hooks": [cmd("BeforeAgent")]}],
        "BeforeTool": [{"matcher": "run_shell_command|write_file|replace", "hooks": [cmd("BeforeTool")]}],
        "AfterTool": [{"matcher": "run_shell_command|write_file|replace", "hooks": [cmd("AfterTool")]}],
        "AfterAgent": [{"hooks": [cmd("AfterAgent", 150000)]}],
    }
    path = repo / ".gemini" / "settings.json"
    data = _load(path)
    data["hooks"] = _merge(data.get("hooks", {}), ours)
    _save(path, data)
    return path


def _antigravity(repo: Path, url: str) -> Path:
    cmd = lambda e, t=30: {"type": "command", "command": _command(repo, "antigravity", e), "timeout": t}  # noqa: E731
    path = repo / ".agents" / "hooks.json"
    data = _load(path)
    data[MARK] = {
        "PreToolUse": [{"matcher": "run_command|write_to_file|replace_file_content|multi_replace_file_content",
                        "hooks": [cmd("PreToolUse")]}],
        "PostToolUse": [{"matcher": "*", "hooks": [cmd("PostToolUse")]}],
        "Stop": [cmd("Stop", 150)],
    }
    _save(path, data)
    return path


def _copilot(repo: Path, url: str) -> Path:
    def cmd(e: str, t: int = 30) -> dict:
        c = _command(repo, "copilot", e)
        return {"type": "command", "bash": c, "powershell": "& " + c, "timeoutSec": t}

    path = repo / ".github" / "hooks" / "solo-license.json"
    _save(path, {"version": 1, "hooks": {
        "userPromptSubmitted": [cmd("userPromptSubmitted")],
        "preToolUse": [cmd("preToolUse")],
        "postToolUse": [cmd("postToolUse")],
        "agentStop": [cmd("agentStop", 150)],
    }})
    return path


def _grok(repo: Path, url: str) -> Path:
    http = lambda e, t=30: {"type": "http", "url": f"{url}/api/hooks/grok/{e}", "timeout": t}  # noqa: E731
    path = repo / ".grok" / "hooks" / "solo-license.json"
    _save(path, {"hooks": {
        "UserPromptSubmit": [{"hooks": [http("UserPromptSubmit")]}],
        "PreToolUse": [{"matcher": "*", "hooks": [http("PreToolUse")]}],
        "PostToolUse": [{"matcher": "*", "hooks": [http("PostToolUse")]}],
        "Stop": [{"hooks": [http("Stop", 150)]}],
    }})
    return path


def _windsurf(repo: Path, url: str) -> Path:
    events = ("pre_user_prompt", "pre_run_command", "pre_write_code", "post_run_command",
              "post_write_code", "post_cascade_response")
    ours = {e: [{"command": _command(repo, "windsurf", e), "show_output": True}] for e in events}
    path = repo / ".windsurf" / "hooks.json"
    data = _load(path)
    data["hooks"] = _merge(data.get("hooks", {}), ours)
    _save(path, data)
    return path


def _kiro(repo: Path, url: str) -> Path:
    path = repo / ".kiro" / "hooks" / "solo-license.json"
    _save(path, {"version": "v1", "hooks": [
        {"name": f"{MARK}-{e.lower()}", "trigger": e, "matcher": "*",
         "action": {"type": "command", "command": _command(repo, "kiro", e)}, "timeout": 150 if e == "Stop" else 60}
        for e in ("UserPromptSubmit", "PreToolUse", "PostToolUse", "Stop")
    ]})
    return path


def _cline(repo: Path, url: str) -> Path:
    folder = repo / ".clinerules" / "hooks"
    folder.mkdir(parents=True, exist_ok=True)
    for event in ("UserPromptSubmit", "PreToolUse", "PostToolUse", "TaskComplete"):
        script = folder / event
        python, hook = _paths(repo)
        # A POSIX script: single-quote each path so nothing in it is expanded.
        script.write_text(f"#!/bin/sh\n# {MARK}\nexec {shlex.quote(python)} {shlex.quote(hook)} cline {event}\n",
                          encoding="utf-8")
        script.chmod(script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return folder


OPENCODE_PLUGIN = """// solo-license: earned autonomy for OpenCode (any model: Groq, GLM, Claude, ...)
import type { Plugin } from "@opencode-ai/plugin"

const BASE: string = process.env.SOLO_LICENSE_URL ?? __URL__

async function gate(event: string, body: unknown): Promise<any> {
  try {
    const r = await fetch(`${BASE}/api/hooks/opencode/${event}`, {
      method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body),
    })
    return await r.json()
  } catch {
    return {} // Solo License is down: OpenCode's own permission rules decide
  }
}

export const SoloLicense: Plugin = async ({ directory }) => ({
  "tool.execute.before": async (input: any, output: any) => {
    const d = await gate("tool.execute.before", { tool_name: input.tool, tool_input: output.args, sessionID: input.sessionID, cwd: directory })
    if (d?.decision === "deny") throw new Error(d.reason ?? "Blocked by Solo License")
  },
  "tool.execute.after": async (input: any, output: any) => {
    await gate("tool.execute.after", { tool_name: input.tool, tool_input: output?.args ?? {}, sessionID: input.sessionID, cwd: directory, result: output?.metadata })
  },
  event: async ({ event }: any) => {
    if (event?.type === "session.idle") await gate("session.idle", { sessionID: event.properties?.sessionID, cwd: directory })
  },
})
"""


def _opencode(repo: Path, url: str) -> Path:
    path = repo / ".opencode" / "plugins" / "solo-license.ts"
    path.parent.mkdir(parents=True, exist_ok=True)
    # The URL goes in as a JSON string literal, never into a template literal.
    path.write_text(OPENCODE_PLUGIN.replace("__URL__", json.dumps(validate_url(url))), encoding="utf-8")
    return path


WRITERS = {
    "claude-code": _claude, "codex": _codex, "cursor": _cursor, "gemini": _gemini, "antigravity": _antigravity,
    "copilot": _copilot, "grok": _grok, "windsurf": _windsurf, "kiro": _kiro, "cline": _cline,
    "opencode": _opencode,
}


def detect(repo: Path) -> list[str]:
    """Agents that already leave a trace in this repo or on this machine."""
    home = Path.home()
    probes = {
        "claude-code": [repo / ".claude", home / ".claude"],
        "codex": [repo / ".codex", home / ".codex"],
        "cursor": [repo / ".cursor", home / ".cursor"],
        "gemini": [repo / ".gemini", home / ".gemini" / "settings.json"],
        "antigravity": [repo / ".agents", home / ".gemini" / "antigravity-cli"],
        "copilot": [home / ".copilot"],
        "grok": [repo / ".grok", home / ".grok"],
        "windsurf": [repo / ".windsurf", home / ".codeium" / "windsurf"],
        "kiro": [repo / ".kiro", home / ".kiro"],
        "cline": [repo / ".clinerules", home / "Documents" / "Cline"],
        "opencode": [repo / ".opencode", home / ".config" / "opencode"],
    }
    return [agent for agent, paths in probes.items() if any(p.exists() for p in paths)]


def install(repo: Path, base_url: str = DEFAULT_URL, agent: str = "claude-code") -> Path:
    spec: AgentSpec = resolve(agent)
    url = validate_url(base_url)
    if spec.transport == "command":
        _shim(repo)
    return WRITERS[spec.key](repo, url)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Install Solo License's hooks for a coding agent.")
    parser.add_argument("repo", type=Path, nargs="?", default=Path("."))
    parser.add_argument("--agent", default="claude-code",
                        help=f"one of: {', '.join(AGENTS)}, or 'auto' / 'all'")
    parser.add_argument("--url", default=os.environ.get("SOLO_LICENSE_URL", DEFAULT_URL))
    args = parser.parse_args(argv)
    repo = args.repo.resolve()
    agents = (detect(repo) or ["claude-code"]) if args.agent == "auto" else \
        list(AGENTS) if args.agent == "all" else [args.agent]
    for name in agents:
        spec = resolve(name)
        path = install(repo, args.url, spec.key)
        print(f"  {spec.label:<34} {path.relative_to(repo) if path.is_relative_to(repo) else path}")
        if spec.notes:
            print(f"  {'':<34} note: {spec.notes}")
    print(f"\nHooks call {args.url}. Start it with: solo-license serve")


if __name__ == "__main__":
    main()
