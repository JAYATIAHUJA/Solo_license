"""``solo-license init --global``: Solo License's hooks for every repository on this machine.

Each agent's *user-level* hook file (``~/.claude/settings.json``,
``~/.codex/hooks.json``, ...) gets the same entries ``init`` writes into a
repository, merged with whatever is already there. Agents whose hooks run a
command share one shim at ``~/.solo-license/hook.py``; the repository is
found at hook time from the payload's working directory. ``--dry-run`` shows
the diff, ``--remove`` takes our entries out again. Standard library only.
"""

from __future__ import annotations

import os
from pathlib import Path

from sololicense.coding import install as repo_install
from sololicense.coding.agents import AGENTS, resolve
from sololicense.coding.install import MARK, Change, apply, diff, plan_agent, shim_changes, validate_url

# Where each agent documents its user-level hooks.
GLOBAL_DOCS = {
    "claude-code": "https://code.claude.com/docs/en/hooks",
    "codex": "https://developers.openai.com/codex/hooks",
    "cursor": "https://cursor.com/docs/hooks",
    "gemini": "https://geminicli.com/docs/hooks/reference/",
    "antigravity": "https://antigravity.google/docs/hooks.md",
    "copilot": "https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-hooks-reference",
    "grok": "https://docs.x.ai/build/features/hooks",
    "windsurf": "https://docs.windsurf.com/windsurf/cascade/hooks",
    "kiro": "https://kiro.dev/docs/hooks/",
    "cline": "https://github.com/cline/cline/blob/main/.clinerules/hooks/README.md",
    "opencode": "https://opencode.ai/docs/plugins",
}

GLOBAL_NOTES = {
    "codex": "Trust the new user hooks once with /hooks. /prompts:trust shows this repo's levels.",
    "cursor": "Type /trust in Agent chat to see this repo's levels.",
    "kiro": "Global hooks need Kiro IDE 1.0.182+ or Kiro CLI 2.13+.",
    "cline": "Enable Hooks in Cline's settings. Cline hooks do not run on Windows.",
    "grok": "Grok also reads ~/.claude/settings.json; if Claude Code is wired too, turn that compatibility off.",
}


def home() -> Path:
    return Path.home()


def solo_home() -> Path:
    """Where Solo License keeps its own user-level files (shim, database, gate pid and log)."""
    return Path(os.environ.get("SOLO_LICENSE_HOME") or home() / ".solo-license")


def _dir(env: str, default: Path) -> Path:
    value = os.environ.get(env, "").strip()
    return Path(value) if value else default


def _codex_home() -> Path:
    return _dir("CODEX_HOME", home() / ".codex")


def global_path(agent: str) -> Path:
    h = home()
    return {
        "claude-code": _dir("CLAUDE_CONFIG_DIR", h / ".claude") / "settings.json",
        "codex": _codex_home() / "hooks.json",
        "cursor": h / ".cursor" / "hooks.json",
        "gemini": h / ".gemini" / "settings.json",
        "antigravity": h / ".gemini" / "config" / "hooks.json",
        "copilot": _dir("COPILOT_HOME", h / ".copilot") / "hooks" / "solo-license.json",
        "grok": h / ".grok" / "hooks" / "solo-license.json",
        "windsurf": h / ".codeium" / "windsurf" / "hooks.json",
        "kiro": h / ".kiro" / "hooks" / "solo-license.json",
        "cline": h / "Documents" / "Cline" / "Hooks",
        "opencode": h / ".config" / "opencode" / "plugins" / "solo-license.ts",
    }[resolve(agent).key]


def hook_path() -> Path:
    return solo_home() / "hook.py"


def detect() -> list[str]:
    """Agents whose user-level folder exists on this machine."""
    h = home()
    probes = {
        "claude-code": [_dir("CLAUDE_CONFIG_DIR", h / ".claude")],
        "codex": [_codex_home()],
        "cursor": [h / ".cursor"],
        "gemini": [h / ".gemini" / "settings.json"],
        "antigravity": [h / ".gemini" / "config", h / ".gemini" / "antigravity-cli"],
        "copilot": [_dir("COPILOT_HOME", h / ".copilot")],
        "grok": [h / ".grok"],
        "windsurf": [h / ".codeium" / "windsurf"],
        "kiro": [h / ".kiro"],
        "cline": [h / "Documents" / "Cline"],
        "opencode": [h / ".config" / "opencode"],
    }
    return [agent for agent, paths in probes.items() if any(p.exists() for p in paths)]


# --- /trust for agents that take user-level slash commands ------------------------

def _trust_steps(url: str) -> str:
    return f"""Show what the coding agent may do alone in the current repository, according to Solo License.

1. Find the repository name: the last folder of `git rev-parse --show-toplevel` (or of the working directory if that fails).
2. Fetch {url}/api/coding?repo=REPO_NAME with REPO_NAME replaced by that name: `curl -s` on macOS and Linux, `Invoke-RestMethod` in Windows PowerShell. Read-only; nothing else to run.
3. Show a short table from its `licenses`: action class, level (L0 asks every time, L1 auto-allows approved command families, L2 auto-allows the whole class), verified and failed runs, and how many verified runs the next level needs.
4. If the request fails, the gate is not running: tell the user to run `solo-license serve --background`, then `solo-license doctor`.
"""


def _codex_prompt(url: str) -> str:
    # Codex expands $1..$9 and $NAME in prompts, so the text holds no dollar sign.
    return ("---\ndescription: Solo License - what the agent may do alone in this repository\n---\n\n"
            + _trust_steps(url))


def _cursor_skill(url: str) -> str:
    return ("---\nname: trust\ndescription: Solo License - show what the agent may do alone in this repository "
            "and how far each action class is from the next level. Use only when the user types /trust.\n---\n\n"
            + _trust_steps(url))


def _extras(agent: str, url: str, remove: bool) -> list[Change]:
    files = {
        "codex": [(_codex_home() / "prompts" / "trust.md", _codex_prompt(url))],
        "cursor": [(home() / ".cursor" / "skills" / "trust" / "SKILL.md", _cursor_skill(url))],
    }.get(agent, [])
    changes = []
    for path, text in files:
        current = path.read_text(encoding="utf-8", errors="ignore") if path.is_file() else ""
        if path.exists() and MARK not in current:
            continue  # someone else's /trust: leave it alone
        change = Change(path, None if remove else text)
        if change.changed:
            changes.append(change)
    return changes


# --- plan, apply ---------------------------------------------------------------------

def plan(agents: list[str], url: str, remove: bool = False) -> list[Change]:
    """Every file change that wires (or unwires) ``agents`` at user level."""
    url = validate_url(url)
    keys = list(dict.fromkeys(resolve(a).key for a in agents))
    hook = hook_path()
    changes: list[Change] = []
    for key in keys:
        changes += plan_agent(key, global_path(key), url, hook, remove)
        changes += _extras(key, url, remove)
    if remove:
        if set(keys) == set(AGENTS):
            changes += shim_changes(hook, remove=True)
    elif any(AGENTS[k].transport == "command" for k in keys):
        changes = shim_changes(hook) + changes
    return changes


def run(agent: str = "auto", url: str = repo_install.DEFAULT_URL, dry_run: bool = False,
        remove: bool = False) -> int:
    if agent == "all" or (remove and agent == "auto"):
        agents = list(AGENTS)
    elif agent == "auto":
        agents = detect() or ["claude-code"]
    else:
        agents = [resolve(agent).key]
    changes = plan(agents, url, remove=remove)
    if dry_run:
        print(diff(changes) or "Nothing to change.")
        return 0
    verbs = {c.path: c.verb for c in changes}
    apply(changes)
    for path, verb in verbs.items():
        print(f"  {verb:<7} {path}")
    if remove:
        print("Removed Solo License's user-level hooks." if changes else "No user-level Solo License hooks found.")
        return 0
    print("" if changes else "  Already up to date.")
    for key in agents:
        spec = AGENTS[key]
        print(f"  {spec.label:<34} {global_path(key)}")
        if key in GLOBAL_NOTES:
            print(f"  {'':<34} note: {GLOBAL_NOTES[key]}")
    print(f"\nEvery repository on this machine now calls {url}.")
    print("Next: solo-license serve --background, then solo-license doctor.")
    return 0
