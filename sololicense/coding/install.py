"""Install Solo License's hooks for a coding agent in one repository.

    solo-license init --agent codex            # or: python -m sololicense.coding.install . --agent codex

Writes that agent's own hook configuration (merged with whatever is already
there, such as Entire's hooks) and, for agents whose hooks run commands, a
one-file shim at ``.solo-license/hook.py``. Running it twice changes nothing.
Every write is first planned as a list of :class:`Change`, so the same plan
can be shown as a diff (``--dry-run``) or undone (``--remove``). The
user-level variant (``init --global``) lives in ``global_install``.
Standard library only.
"""

from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import shlex
import stat
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

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
    path.write_text(_json_text(data), encoding="utf-8")


def _json_text(data: dict) -> str:
    return json.dumps(data, indent=2) + "\n"


def _ours(entry) -> bool:
    return MARK in json.dumps(entry) or "/api/hooks/" in json.dumps(entry)


def _merge(existing: dict, ours: dict) -> dict:
    """Event -> list merge that replaces only our previous entries."""
    for event, entries in ours.items():
        kept = [e for e in existing.get(event, []) if not _ours(e)]
        existing[event] = kept + entries
    return existing


def _unmerge(existing: dict) -> dict:
    """``existing`` without our entries; events left empty are dropped."""
    out = {}
    for event, entries in existing.items():
        kept = [e for e in entries if not _ours(e)] if isinstance(entries, list) else entries
        if kept:
            out[event] = kept
    return out


@dataclass(frozen=True)
class Change:
    """One file the installer would write (``text``) or delete (``text is None``)."""

    path: Path
    text: str | None
    executable: bool = False
    brief: bool = False        # show only a summary in a diff (the copied shim)

    def before(self) -> str:
        return self.path.read_text(encoding="utf-8", errors="replace") if self.path.is_file() else ""

    @property
    def changed(self) -> bool:
        if self.text is None:
            return self.path.exists()
        return not self.path.is_file() or self.before() != self.text

    @property
    def verb(self) -> str:
        return "remove" if self.text is None else ("update" if self.path.exists() else "create")


def apply(changes: list[Change]) -> None:
    for change in changes:
        if change.text is None:
            if change.path.is_file():
                change.path.unlink()
            continue
        change.path.parent.mkdir(parents=True, exist_ok=True)
        # Scripts keep LF line endings: a CRLF shebang does not run.
        change.path.write_text(change.text, encoding="utf-8", newline="\n" if change.executable else None)
        if change.executable:
            change.path.chmod(change.path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def diff(changes: list[Change]) -> str:
    out: list[str] = []
    for change in changes:
        exists = change.path.exists()
        before, after = change.before(), change.text or ""
        old = str(change.path) if exists else "/dev/null"
        new = str(change.path) if change.text is not None else "/dev/null"
        if change.brief:
            out.append(f"--- {old}\n+++ {new}\n@@ {change.verb} ({len(after.splitlines())} lines) @@\n")
            continue
        for line in difflib.unified_diff(before.splitlines(True), after.splitlines(True), old, new):
            out.append(line if line.endswith("\n") else line + "\n")
    return "".join(out)


# --- planners: how each kind of config file is merged ------------------------------

def _events(path: Path, ours: dict, remove: bool, defaults: dict | None = None) -> list[Change]:
    """A JSON file with a top-level ``hooks`` object of event -> list (shared with other tools)."""
    data = _load(path)
    hooks = data.get("hooks", {}) if isinstance(data.get("hooks"), dict) else {}
    if remove:
        left = _unmerge(hooks)
        if not path.exists() or left == hooks:
            return []
        data = {**data, "hooks": left} if left else {k: v for k, v in data.items() if k != "hooks"}
        if not data or data == (defaults or {}):
            return [Change(path, None)]
        return [Change(path, _json_text(data))]
    new = {**(defaults or {}), **data, "hooks": _merge(json.loads(json.dumps(hooks)), ours)}
    return [] if path.exists() and new == data else [Change(path, _json_text(new))]


def _block(path: Path, ours: dict, remove: bool) -> list[Change]:
    """A JSON file of named hook blocks: ours sits under the ``solo-license`` key."""
    data = _load(path)
    if remove:
        if MARK not in data:
            return []
        data = {k: v for k, v in data.items() if k != MARK}
        return [Change(path, _json_text(data) if data else None)]
    if data.get(MARK) == ours:
        return []
    return [Change(path, _json_text({**data, MARK: ours}))]


def _owned(path: Path, text: str, remove: bool, executable: bool = False) -> list[Change]:
    """A file that is entirely ours."""
    if remove:
        current = path.read_text(encoding="utf-8", errors="ignore") if path.is_file() else ""
        return [Change(path, None)] if MARK in current or "/api/hooks/" in current else []
    return [Change(path, text, executable=executable)]


# --- per agent ------------------------------------------------------------------

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


def _paths(hook: Path) -> tuple[str, str]:
    return _safe_path(str(sys.executable), "Python"), _safe_path(str(hook), "hook")


Command = Callable[[str], str]


def _commander(hook: Path, agent: str) -> Command:
    """``"<python>" "<hook.py>" <agent> <event>``. Paths are double-quoted for
    spaces (accepted by sh, bash, PowerShell and cmd) and checked to hold
    nothing a shell would expand. The trailing comment marks the entry as
    ours so a re-install replaces it."""
    python, path = _paths(hook)
    return lambda event: '"' + python + '" "' + path + '" ' + agent + " " + event + " # " + MARK


def _claude(path: Path, url: str, hook: Path, remove: bool) -> list[Change]:
    def http(event: str, timeout: int = 10) -> dict:
        return {"type": "http", "url": f"{url}/api/hooks/{event}", "timeout": timeout,
                "headers": {"X-Solo-Hook-Key": "$SOLO_HOOK_KEY"}, "allowedEnvVars": ["SOLO_HOOK_KEY"]}

    ours = {
        "UserPromptSubmit": [{"hooks": [http("user-prompt")]}],
        # Every tool: a loop stop refuses any call, and MCP tools can run shell commands too.
        "PreToolUse": [{"matcher": "*", "hooks": [http("pre-tool")]}],
        "PermissionRequest": [{"matcher": "*", "hooks": [http("permission")]}],
        "PostToolUse": [{"matcher": "*", "hooks": [http("post-tool")]}],
        "PostToolUseFailure": [{"matcher": "*", "hooks": [http("post-tool-failure")]}],
        "Stop": [{"hooks": [http("stop", 150)]}],
        "SubagentStart": [{"hooks": [http("subagent-start")]}],
        "SubagentStop": [{"hooks": [http("subagent-stop", 150)]}],
    }
    return _events(path, ours, remove)


def _codex(path: Path, url: str, hook: Path, remove: bool) -> list[Change]:
    run = _commander(hook, "codex")
    cmd = lambda e, t=30: {"type": "command", "command": run(e), "timeout": t}  # noqa: E731
    ours = {
        "UserPromptSubmit": [{"hooks": [cmd("UserPromptSubmit")]}],
        "PermissionRequest": [{"matcher": "*", "hooks": [cmd("PermissionRequest")]}],
        "PostToolUse": [{"matcher": "*", "hooks": [cmd("PostToolUse")]}],
        "Stop": [{"hooks": [cmd("Stop", 150)]}],
        "SubagentStart": [{"hooks": [cmd("SubagentStart")]}],
        "SubagentStop": [{"hooks": [cmd("SubagentStop", 150)]}],
    }
    return _events(path, ours, remove)


def _cursor(path: Path, url: str, hook: Path, remove: bool) -> list[Change]:
    run = _commander(hook, "cursor")
    cmd = lambda e, **kw: {"command": run(e), **kw}  # noqa: E731
    ours = {
        "beforeSubmitPrompt": [cmd("beforeSubmitPrompt")],
        "beforeShellExecution": [cmd("beforeShellExecution")],
        "preToolUse": [cmd("preToolUse", matcher="Write|Delete")],
        "afterShellExecution": [cmd("afterShellExecution")],
        "afterFileEdit": [cmd("afterFileEdit")],
        "stop": [cmd("stop")],
        "subagentStart": [cmd("subagentStart")],
        "subagentStop": [cmd("subagentStop")],
    }
    return _events(path, ours, remove, defaults={"version": 1})


def _gemini(path: Path, url: str, hook: Path, remove: bool) -> list[Change]:
    run = _commander(hook, "gemini")
    cmd = lambda e, t=30000: {"name": MARK, "type": "command", "command": run(e), "timeout": t}  # noqa: E731
    ours = {
        "BeforeAgent": [{"hooks": [cmd("BeforeAgent")]}],
        "BeforeTool": [{"matcher": "run_shell_command|write_file|replace", "hooks": [cmd("BeforeTool")]}],
        "AfterTool": [{"matcher": "run_shell_command|write_file|replace", "hooks": [cmd("AfterTool")]}],
        "AfterAgent": [{"hooks": [cmd("AfterAgent", 150000)]}],
    }
    return _events(path, ours, remove)


def _antigravity(path: Path, url: str, hook: Path, remove: bool) -> list[Change]:
    run = _commander(hook, "antigravity")
    cmd = lambda e, t=30: {"type": "command", "command": run(e), "timeout": t}  # noqa: E731
    ours = {
        "PreToolUse": [{"matcher": "run_command|write_to_file|replace_file_content|multi_replace_file_content",
                        "hooks": [cmd("PreToolUse")]}],
        "PostToolUse": [{"matcher": "*", "hooks": [cmd("PostToolUse")]}],
        "Stop": [cmd("Stop", 150)],
    }
    return _block(path, ours, remove)


def _copilot(path: Path, url: str, hook: Path, remove: bool) -> list[Change]:
    run = _commander(hook, "copilot")

    def cmd(e: str, t: int = 30) -> dict:
        c = run(e)
        return {"type": "command", "bash": c, "powershell": "& " + c, "timeoutSec": t}

    return _owned(path, _json_text({"version": 1, "hooks": {
        "userPromptSubmitted": [cmd("userPromptSubmitted")],
        "preToolUse": [cmd("preToolUse")],
        "postToolUse": [cmd("postToolUse")],
        "agentStop": [cmd("agentStop", 150)],
    }}), remove)


def _grok(path: Path, url: str, hook: Path, remove: bool) -> list[Change]:
    http = lambda e, t=30: {"type": "http", "url": f"{url}/api/hooks/grok/{e}", "timeout": t}  # noqa: E731
    return _owned(path, _json_text({"hooks": {
        "UserPromptSubmit": [{"hooks": [http("UserPromptSubmit")]}],
        "PreToolUse": [{"matcher": "*", "hooks": [http("PreToolUse")]}],
        "PostToolUse": [{"matcher": "*", "hooks": [http("PostToolUse")]}],
        "Stop": [{"hooks": [http("Stop", 150)]}],
    }}), remove)


def _windsurf(path: Path, url: str, hook: Path, remove: bool) -> list[Change]:
    run = _commander(hook, "windsurf")
    events = ("pre_user_prompt", "pre_run_command", "pre_write_code", "post_run_command",
              "post_write_code", "post_cascade_response")
    # On Windows Windsurf runs `powershell -Command`, where a quoted path only runs behind `&`.
    ours = {e: [{"command": run(e), "powershell": "& " + run(e), "show_output": True}] for e in events}
    return _events(path, ours, remove)


def _kiro(path: Path, url: str, hook: Path, remove: bool) -> list[Change]:
    run = _commander(hook, "kiro")
    return _owned(path, _json_text({"version": "v1", "hooks": [
        {"name": f"{MARK}-{e.lower()}", "trigger": e, "matcher": "*",
         "action": {"type": "command", "command": run(e)}, "timeout": 150 if e == "Stop" else 60}
        for e in ("UserPromptSubmit", "PreToolUse", "PostToolUse", "Stop")
    ]}), remove)


def _cline(folder: Path, url: str, hook: Path, remove: bool) -> list[Change]:
    python, path = _paths(hook)
    changes: list[Change] = []
    for event in ("UserPromptSubmit", "PreToolUse", "PostToolUse", "TaskComplete"):
        # A POSIX script: single-quote each path so nothing in it is expanded.
        text = f"#!/bin/sh\n# {MARK}\nexec {shlex.quote(python)} {shlex.quote(path)} cline {event}\n"
        changes += _owned(folder / event, text, remove, executable=True)
    return changes


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


def _opencode(path: Path, url: str, hook: Path, remove: bool) -> list[Change]:
    # The URL goes in as a JSON string literal, never into a template literal.
    return _owned(path, OPENCODE_PLUGIN.replace("__URL__", json.dumps(url)), remove)


PLANNERS: dict[str, Callable[[Path, str, Path, bool], list[Change]]] = {
    "claude-code": _claude, "codex": _codex, "cursor": _cursor, "gemini": _gemini, "antigravity": _antigravity,
    "copilot": _copilot, "grok": _grok, "windsurf": _windsurf, "kiro": _kiro, "cline": _cline,
    "opencode": _opencode,
}


def plan_agent(agent: str, target: Path, url: str, hook: Path, remove: bool = False) -> list[Change]:
    """The changes that wire (or unwire) ``agent`` through the config at ``target``."""
    spec = resolve(agent)
    return [c for c in PLANNERS[spec.key](target, validate_url(url), hook, remove) if c.changed]


def shim_changes(hook: Path, remove: bool = False) -> list[Change]:
    change = Change(hook, None if remove else SHIM_SOURCE.read_text(encoding="utf-8"), brief=True)
    return [change] if change.changed else []


# --- one repository ---------------------------------------------------------------

def _repo_hook(repo: Path) -> Path:
    return repo / ".solo-license" / "hook.py"


def _shim(repo: Path) -> Path:
    # Ignore the machine-specific shim; .solo-license/policy.toml is for committing.
    apply(shim_changes(_repo_hook(repo)) + [Change(repo / ".solo-license" / ".gitignore", "hook.py\n")])
    return _repo_hook(repo)


def plan(repo: Path, base_url: str = DEFAULT_URL, agent: str = "claude-code", remove: bool = False) -> list[Change]:
    spec = resolve(agent)
    return plan_agent(spec.key, repo / spec.config_path, base_url, _repo_hook(repo), remove)


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
    validate_url(base_url)
    if spec.transport == "command":
        _shim(repo)
    apply(plan(repo, base_url, spec.key))
    return repo / spec.config_path


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Install Solo License's hooks for a coding agent.")
    parser.add_argument("repo", type=Path, nargs="?", default=Path("."))
    parser.add_argument("--agent", default="claude-code",
                        help=f"one of: {', '.join(AGENTS)}, or 'auto' / 'all'")
    parser.add_argument("--url", default=os.environ.get("SOLO_LICENSE_URL", DEFAULT_URL))
    parser.add_argument("--dry-run", action="store_true", help="print the changes as a diff; write nothing")
    parser.add_argument("--remove", action="store_true", help="take Solo License's hooks out again")
    args = parser.parse_args(argv)
    repo = args.repo.resolve()
    agents = (detect(repo) or ["claude-code"]) if args.agent == "auto" else \
        list(AGENTS) if args.agent == "all" else [args.agent]
    if args.dry_run or args.remove:
        changes = [c for name in agents for c in plan(repo, args.url, name, remove=args.remove)]
        if not args.remove and any(resolve(a).transport == "command" for a in agents):
            changes = shim_changes(_repo_hook(repo)) + changes
        if args.dry_run:
            print(diff(changes) or "Nothing to change.")
            return
        apply(changes)
        for change in changes:
            print(f"  {change.verb:<7} {change.path}")
        print("Removed Solo License's hooks." if changes else "No Solo License hooks found.")
        return
    for name in agents:
        spec = resolve(name)
        path = install(repo, args.url, spec.key)
        print(f"  {spec.label:<34} {path.relative_to(repo) if path.is_relative_to(repo) else path}")
        if spec.notes:
            print(f"  {'':<34} note: {spec.notes}")
    print(f"\nHooks call {args.url}. Start it with: solo-license serve")


if __name__ == "__main__":
    main()
