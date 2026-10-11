"""Map a coding agent's tool call to an action class.

Trust is earned per *class*, not per command: ``npm test``, ``pytest`` and
``cargo test`` all build the same ``test-run`` record, so an agent earns a
license in a handful of runs instead of one per spelling. Rules are checked
first and decide nearly every call in microseconds; only commands no rule
recognises are left ``unknown`` for the calibrated classifier (:mod:`jev`).

A chained command (``npm test && rm -rf build``) is split and every part is
classified: the riskiest part decides, so a safe prefix can never carry a
dangerous suffix through the gate.
"""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass


@dataclass(frozen=True)
class ActionClass:
    key: str
    label: str
    risk: int            # 0 harmless .. 5 irreversible; orders "riskiest part wins"
    max_level: int       # highest level this class may ever earn (0 = always ask)
    incident_cost: float  # USD cost of one unattended mistake, for the trust ladder


ACTION_CLASSES: dict[str, ActionClass] = {c.key: c for c in (
    ActionClass("read", "Read files and status", 0, 2, 0.5),
    ActionClass("test-run", "Run tests", 1, 2, 1.0),
    ActionClass("lint-format", "Lint and format", 1, 2, 1.0),
    ActionClass("build", "Build", 1, 2, 2.0),
    ActionClass("file-edit", "Edit files", 2, 2, 5.0),
    ActionClass("git-local", "Local git (add, commit, branch)", 2, 2, 5.0),
    ActionClass("install-dep", "Install dependencies", 3, 2, 20.0),
    ActionClass("network-fetch", "Fetch from the network", 3, 1, 50.0),
    ActionClass("git-remote", "Push to a remote", 4, 1, 200.0),
    ActionClass("file-delete", "Delete files", 4, 0, 500.0),
    ActionClass("deploy", "Deploy or publish", 5, 0, 2000.0),
    ActionClass("db-migrate", "Change a database", 5, 0, 2000.0),
    ActionClass("unknown", "Unrecognised command", 5, 0, 500.0),
)}


@dataclass(frozen=True)
class Classification:
    action_class: str
    pattern: str            # the command family a level-1 license covers, e.g. "npm test"
    source: str             # rules | jev | fallback
    confidence: float = 1.0
    hard_deny: str = ""     # non-empty: never allowed, whatever the license says
    irreversible: float | None = None  # Jev's probability, when it was asked

    @property
    def spec(self) -> ActionClass:
        return ACTION_CLASSES[self.action_class]


# Never allowed: these destroy data outside git or run code nobody reviewed.
HARD_DENY: tuple[tuple[str, re.Pattern], ...] = (
    ("deletes the filesystem root or home",
     re.compile(r"\brm\s+(-[a-z]*r[a-z]*f|-[a-z]*f[a-z]*r|-r\s+-f|-f\s+-r)\b[^|;&]*\s(/|~|\$HOME)(\s|$|/\*)")),
    ("pipes downloaded code into a shell",
     re.compile(r"\b(curl|wget)\b[^|]*\|\s*(sudo\s+)?(ba|z|da)?sh\b")),
    ("force-pushes a protected branch",
     re.compile(r"\bgit\s+push\b(?=.*(--force\b|-f\b|--force-with-lease))(?=.*\b(main|master)\b)")),
    ("runs as root", re.compile(r"(^|\s)sudo\s")),
    ("formats or overwrites a disk", re.compile(r"\b(mkfs(\.\w+)?|dd\s+if=.*\bof=/dev/)")),
    ("drops a database", re.compile(r"\bdrop\s+(database|schema)\b", re.I)),
)

_SPLIT = re.compile(r"\s*(?:&&|\|\||;|\||\n)\s*")

# (class, regex on the normalised command). First match wins, so order matters.
_RULES: tuple[tuple[str, re.Pattern], ...] = tuple((c, re.compile(p)) for c, p in (
    ("db-migrate", r"^(alembic|prisma\s+migrate|rails\s+db:|knex\s+migrate|python\s+manage\.py\s+migrate|psql|mysql)\b"),
    ("deploy", r"^(vercel|netlify|fly|flyctl|heroku|kubectl\s+(apply|delete|rollout)|helm\s+(install|upgrade)|"
               r"terraform\s+(apply|destroy)|npm\s+publish|yarn\s+publish|pnpm\s+publish|twine\s+upload|"
               r"cargo\s+publish|docker\s+push|gh\s+release)\b"),
    ("git-remote", r"^git\s+(push|pull|fetch|clone)\b|^gh\s+(pr\s+(create|merge)|repo)\b"),
    ("file-delete", r"^(rm|rmdir|del|shred|unlink)\b|^git\s+(clean|rm)\b|^git\s+reset\s+--hard\b|^git\s+checkout\s+--\s"),
    ("git-local", r"^git\s+(add|commit|branch|checkout|switch|merge|rebase|stash|tag|restore|cherry-pick|revert|reset)\b"),
    ("read", r"^git\s+(status|diff|log|show|blame|rev-parse|ls-files|remote\s+-v)\b"),
    ("test-run", r"^((npm|pnpm|yarn|bun)\s+(run\s+)?test|npx\s+(jest|vitest|playwright\s+test)|pytest|python3?\s+-m\s+(pytest|unittest)|"
                 r"go\s+test|cargo\s+test|mvn\s+test|gradle\s+test|dotnet\s+test|rspec|phpunit|make\s+test|node\s+--test|tox)\b"),
    ("lint-format", r"^((npm|pnpm|yarn)\s+(run\s+)?(lint|format|typecheck)|npx\s+(eslint|prettier|tsc)|eslint|prettier|ruff|black|"
                    r"isort|flake8|mypy|pyright|tsc|gofmt|go\s+vet|cargo\s+(fmt|clippy)|rubocop)\b"),
    ("build", r"^((npm|pnpm|yarn|bun)\s+(run\s+)?(build|dev|start)|npx\s+vite|vite|make|cargo\s+build|go\s+build|"
              r"mvn\s+(package|compile)|gradle\s+build|dotnet\s+build|docker\s+build|tsc\s+-b)\b"),
    ("install-dep", r"^((npm|pnpm|yarn|bun)\s+(install|i|add|ci)|pip3?\s+install|python3?\s+-m\s+pip\s+install|"
                    r"uv\s+(add|pip\s+install|sync)|poetry\s+(add|install)|cargo\s+add|go\s+get|gem\s+install|"
                    r"bundle\s+install|composer\s+(install|require)|brew\s+install|apt(-get)?\s+install)\b"),
    ("network-fetch", r"^(curl|wget|http|ssh|scp|rsync|nc|telnet)\b"),
    ("read", r"^(ls|dir|cat|type|head|tail|less|more|wc|find|grep|rg|ag|tree|pwd|echo|which|where|whoami|env|printenv|"
             r"date|file|stat|du|df|sort|uniq|cut|diff|jq|sed\s+-n|awk|node\s+-v|python3?\s+--version|\w+\s+--version)\b"),
))

_READ_TOOLS = {"Read", "Glob", "Grep", "LS", "NotebookRead", "TodoWrite", "TaskCreate", "TaskUpdate"}
_EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
_NETWORK_TOOLS = {"WebFetch", "WebSearch"}
_SHELL_TOOLS = {"Bash", "PowerShell"}

# Leading words that do not change what a command does.
_PREFIXES = re.compile(r"^((\w+=\S*\s+)+|time\s+|nice\s+|env\s+(\w+=\S*\s+)*)")


def _normalise(part: str) -> str:
    part = part.strip().strip("()").strip()
    part = re.sub(r"^cd\s+\S+\s*$", "cd", part)
    return _PREFIXES.sub("", part).strip()


def _pattern(part: str) -> str:
    """Command family a level-1 license covers: the program and its subcommand."""
    try:
        words = shlex.split(part, posix=True)
    except ValueError:
        words = part.split()
    words = [w for w in words if not w.startswith("-")][:2]
    return " ".join(words) or part[:40]


def hard_deny_reason(command: str) -> str:
    for reason, pattern in HARD_DENY:
        if pattern.search(command):
            return reason
    return ""


def classify_command(command: str) -> Classification:
    """Classify a shell command by rules. The riskiest part of a chain decides."""
    denied = hard_deny_reason(command)
    best: tuple[ActionClass, str] | None = None
    for raw in _SPLIT.split(command.strip()):
        part = _normalise(raw)
        if not part or part == "cd":
            continue
        key = next((c for c, rx in _RULES if rx.search(part)), "unknown")
        spec = ACTION_CLASSES[key]
        if best is None or spec.risk > best[0].risk:
            best = (spec, _pattern(part))
    spec, pattern = best or (ACTION_CLASSES["read"], "cd")
    return Classification(spec.key, pattern, "rules", 1.0, hard_deny=denied)


def classify_tool(tool_name: str, tool_input: dict) -> Classification:
    """Classify any Claude Code tool call."""
    if tool_name in _SHELL_TOOLS:
        return classify_command(str(tool_input.get("command", "")))
    if tool_name in _READ_TOOLS:
        return Classification("read", tool_name, "rules")
    if tool_name in _EDIT_TOOLS:
        return Classification("file-edit", tool_name, "rules")
    if tool_name in _NETWORK_TOOLS:
        return Classification("network-fetch", tool_name, "rules")
    return Classification("unknown", tool_name, "rules")


def describe(tool_name: str, tool_input: dict) -> str:
    """One readable line for logs, traces and the UI."""
    if tool_name in _SHELL_TOOLS:
        return str(tool_input.get("command", ""))[:300]
    for key in ("file_path", "notebook_path", "url", "query", "pattern", "path"):
        if tool_input.get(key):
            return f"{tool_name} {tool_input[key]}"[:300]
    return tool_name
