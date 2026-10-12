"""Who decides how far an agent may go: the coding policy.

Three layers, and the strictest always wins:

1. **Built-in** - each action class's ceiling and the hard-deny list in
   :mod:`actions` (deploys always ask, force-pushing main is never allowed).
2. **The repository's policy file**, ``.solo-license/policy.toml``, committed
   with the code so a team reviews privilege changes like any other change::

       [classes]
       install-dep = { max = 1 }      # never past L1 here
       file-edit   = { max = 0 }      # edits always ask

       [deny]
       commands = ["terraform destroy", "kubectl delete *"]
       paths    = [".env", "infra/prod/**"]

       [freeze]
       enabled = false                # true: everything asks

       [tools."mcp__github__*"]       # MCP tools, by a glob on the tool name
       risk = "write"                 # read (up to L2) | write (L1) | destructive (asks)
       [tools."mcp__aws__delete_*"]
       forbidden = true               # optional: ceiling = 0..2 overrides the risk's

3. **This machine's settings** (the dashboard), for one repository or for
   all of them (``"*"``). They can only tighten: a ceiling is the lowest of
   all layers, deny rules add up, and any layer can freeze.

A policy never grants anything: it only lowers ceilings and adds denials.
The one exception is an MCP tool's risk: without a rule it is guessed from the
tool's verb (``list_*`` read, ``merge_*`` destructive), and a rule replaces
the guess. Where several rules match a tool, the strictest wins.
"""

from __future__ import annotations

import fnmatch
import os
import shlex
import hashlib
import json
import sqlite3
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from sololicense.coding.actions import ACTION_CLASSES, MCP_RISKS, mcp_parts, mcp_tool_risk
from sololicense.coding.budget import Limits

POLICY_FILE = Path(".solo-license") / "policy.toml"
ALL_REPOS = "*"
# How far an MCP tool may go by its risk: reads use the whole class (L2), writes
# only once a person approved that tool (L1), destructive tools always ask.
TOOL_CEILINGS = {"read": 2, "write": 1, "destructive": 0}
_TOOL_FIELDS = {"risk", "ceiling", "forbidden"}
MAX_TOOL_RULES = 100

STARTER = """# Solo License policy for this repository. Commit it: privilege changes
# are then reviewed like code. This file can only make the agent ask more,
# never less. Levels: 0 asks every time, 1 runs commands a person approved
# here, 2 runs the whole class. Built-in ceilings still apply.

[classes]
# install-dep = { max = 1 }
# file-edit   = { max = 0 }
# git-remote  = { max = 0 }

[deny]
# Commands never allowed here (substring, or a glob with *).
commands = []
# Files the agent may never edit (globs, relative to the repo root).
paths = [".env", ".env.*"]

[freeze]
# true: every action asks, whatever has been earned.
enabled = false

[subagents]
# Subagents inherit the repo license, capped at this level until they earn
# their own evidence. The cap can only be tightened by policy.
max = 1
[budget]
# USD caps (estimates where the agent does not report its own cost). Past a
# cap only reading is allowed until a person raises it or resumes.
# session_usd = 5
# day_usd     = 25
# warn_at     = 0.8
# MCP tools: each server earns its own license (e.g. "mcp:github" under
# [classes]). Without a rule a tool's risk comes from its verb: list/get/search
# are reads (up to L2), create/update are writes (L1), merge/delete/deploy
# always ask.
# [tools."mcp__github__*"]
# risk = "write"
# [tools."mcp__aws__*"]
# forbidden = true
"""


@dataclass(frozen=True)
class ToolRule:
    """A rule for the tools whose name matches ``pattern`` (a glob)."""

    pattern: str
    risk: str = ""                 # read | write | destructive; "" keeps the verb's
    ceiling: int | None = None     # overrides the risk's ceiling
    forbidden: bool = False

    def matches(self, tool_name: str) -> bool:
        return fnmatch.fnmatchcase(tool_name.lower(), self.pattern.lower())

    def to_json(self) -> dict:
        body: dict = {}
        if self.risk:
            body["risk"] = self.risk
        if self.ceiling is not None:
            body["ceiling"] = self.ceiling
        if self.forbidden:
            body["forbidden"] = True
        return body


class Ceilings(dict):
    """Ceilings per class. A class no layer names - any MCP server - has its
    built-in ceiling (0 when frozen)."""

    def __init__(self, data=(), *, frozen: bool = False):
        super().__init__(data)
        self.frozen = frozen

    def __missing__(self, key):
        return 0 if self.frozen else ACTION_CLASSES[key].max_level


@dataclass(frozen=True)
class Policy:
    """One layer of policy (or the merged, effective one)."""

    ceilings: dict[str, int] = field(default_factory=dict)
    deny_commands: tuple[str, ...] = ()
    deny_paths: tuple[str, ...] = ()
    freeze: bool = False
    source: str = "built-in"
    subagent_max: int = 1
    subagent_deny_types: tuple[str, ...] = ()
    budget: Limits = field(default_factory=Limits)
    tools: tuple[ToolRule, ...] = ()

    def to_json(self) -> dict:
        out = {"ceilings": dict(self.ceilings), "deny_commands": list(self.deny_commands),
               "deny_paths": list(self.deny_paths), "freeze": self.freeze, "source": self.source,
               "tools": {r.pattern: r.to_json() for r in self.tools}}
        out["subagent_max"] = self.subagent_max
        out["subagent_deny_types"] = list(self.subagent_deny_types)
        if self.budget.any:
            out["budget"] = budget_json(self.budget)
        return out

    def to_raw(self) -> dict:
        """This layer in the policy file's own shape (what :func:`_clean` reads)."""
        return {"classes": {k: {"max": v} for k, v in self.ceilings.items()},
                "deny": {"commands": list(self.deny_commands), "paths": list(self.deny_paths)},
                "freeze": {"enabled": self.freeze},
                "subagents": {"max": self.subagent_max, "deny_types": list(self.subagent_deny_types)},
                "budget": budget_json(self.budget),
                "tools": {r.pattern: r.to_json() for r in self.tools}}

    @property
    def digest(self) -> str:
        body = {k: v for k, v in self.to_json().items() if k != "source" and (k != "tools" or v)}
        blob = json.dumps(body, sort_keys=True)
        return hashlib.sha256(blob.encode()).hexdigest()[:12]


def _clean(raw: dict, source: str) -> Policy:
    """Validate one layer. Unknown classes and out-of-range levels are refused."""
    ceilings: dict[str, int] = {}
    for key, value in (raw.get("classes") or {}).items():
        if key not in ACTION_CLASSES:
            raise ValueError(f"{source}: unknown action class '{key}'")
        level = value.get("max") if isinstance(value, dict) else value
        if not isinstance(level, int) or not 0 <= level <= 2:
            raise ValueError(f"{source}: '{key}' max must be 0, 1 or 2")
        ceilings[key] = level
    deny = raw.get("deny") or {}
    commands = tuple(str(c).strip() for c in deny.get("commands", []) if str(c).strip())
    paths = tuple(str(p).strip().replace("\\", "/") for p in deny.get("paths", []) if str(p).strip())
    freeze = raw.get("freeze") or {}
    subagents = raw.get("subagents") or {}
    max_level = subagents.get("max", 1)
    if not isinstance(max_level, int) or not 0 <= max_level <= 2:
        raise ValueError(f"{source}: subagents.max must be 0, 1 or 2")
    deny_types = tuple(str(t).strip() for t in subagents.get("deny_types", ()) if str(t).strip())
    return Policy(ceilings, commands, paths, bool(freeze.get("enabled", False)), source,
                  max_level, deny_types, _clean_budget(raw.get("budget") or {}, source),
                  _clean_tools(raw.get("tools") or {}, source))


def budget_json(limits: Limits) -> dict:
    return {"session_usd": limits.session_usd, "day_usd": limits.day_usd, "warn_at": limits.warn_at}


def _clean_budget(raw: dict, source: str) -> Limits:
    def cap(key: str) -> float | None:
        value = raw.get(key)
        if value is None or value == "":
            return None
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 < value <= 1_000_000:
            raise ValueError(f"{source}: budget {key} must be a positive number of USD")
        return float(value)

    warn = raw.get("warn_at", 0.8)
    if isinstance(warn, bool) or not isinstance(warn, (int, float)) or not 0 < warn < 1:
        raise ValueError(f"{source}: budget warn_at must be between 0 and 1")
    return Limits(cap("session_usd"), cap("day_usd"), float(warn))


def _clean_tools(raw: dict, source: str) -> tuple[ToolRule, ...]:
    if not isinstance(raw, dict) or len(raw) > MAX_TOOL_RULES:
        raise ValueError(f"{source}: [tools] must be at most {MAX_TOOL_RULES} rules")
    rules = []
    for pattern, body in raw.items():
        pattern = str(pattern).strip()
        if not pattern or not isinstance(body, dict):
            raise ValueError(f"{source}: tools.\"{pattern}\" must be a table (risk, ceiling, forbidden)")
        unknown = set(body) - _TOOL_FIELDS
        if unknown:
            raise ValueError(f"{source}: tools.\"{pattern}\" has unknown field(s) {', '.join(sorted(unknown))}")
        risk, ceiling, forbidden = body.get("risk", ""), body.get("ceiling"), body.get("forbidden", False)
        if risk and risk not in MCP_RISKS:
            raise ValueError(f"{source}: tools.\"{pattern}\" risk must be read, write or destructive")
        if ceiling is not None and (not isinstance(ceiling, int) or isinstance(ceiling, bool) or not 0 <= ceiling <= 2):
            raise ValueError(f"{source}: tools.\"{pattern}\" ceiling must be 0, 1 or 2")
        if not isinstance(forbidden, bool):
            raise ValueError(f"{source}: tools.\"{pattern}\" forbidden must be true or false")
        rules.append(ToolRule(pattern, risk, ceiling, forbidden))
    return tuple(rules)


def from_file(root: str | Path) -> Policy | None:
    path = Path(root) / POLICY_FILE
    if not path.is_file():
        return None
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        # A broken team policy must not silently loosen anything: freeze.
        return Policy(freeze=True, source=f"{POLICY_FILE.as_posix()} (unreadable: {error}; frozen)")
    try:
        return _clean(raw, POLICY_FILE.as_posix())
    except ValueError as error:
        return Policy(freeze=True, source=f"{error} (frozen)")


def local(conn: sqlite3.Connection, repo: str) -> Policy | None:
    row = conn.execute("SELECT body FROM agent_policies WHERE repo = ?", (repo,)).fetchone()
    if row is None:
        return None
    return _clean(json.loads(row["body"]), "this machine" if repo == ALL_REPOS else f"this machine ({repo})")


def save_local(conn: sqlite3.Connection, repo: str, raw: dict) -> Policy:
    """Save this machine's layer. A body without ``budget`` keeps the saved caps."""
    if "budget" not in raw:
        before = local(conn, repo)
        raw = {**raw, "budget": budget_json(before.budget) if before else {}}
    policy = _clean(raw, "this machine")
    conn.execute(
        "INSERT INTO agent_policies (repo, body, updated_at) VALUES (?, ?, datetime('now')) "
        "ON CONFLICT (repo) DO UPDATE SET body = excluded.body, updated_at = excluded.updated_at",
        (repo, json.dumps(policy.to_raw())),
    )
    return policy


def merge(*layers: Policy | None) -> Policy:
    """The strictest combination of the given layers."""
    present = [p for p in layers if p is not None]
    ceilings = Ceilings({key: spec.max_level for key, spec in ACTION_CLASSES.items()})
    for p in present:
        for key, level in p.ceilings.items():
            ceilings[key] = min(ceilings[key], level)
    freeze = any(p.freeze for p in present)
    if freeze:
        ceilings = Ceilings({key: 0 for key in ceilings}, frozen=True)
    subagent_max = min((p.subagent_max for p in present), default=1)
    subagent_deny_types = tuple(dict.fromkeys(
        t for p in present for t in p.subagent_deny_types
    ))
    def lowest(values) -> float | None:
        values = [v for v in values if v is not None]
        return min(values) if values else None

    budgets = [p.budget for p in present]
    return Policy(
        ceilings=ceilings,
        deny_commands=tuple(dict.fromkeys(c for p in present for c in p.deny_commands)),
        deny_paths=tuple(dict.fromkeys(x for p in present for x in p.deny_paths)),
        freeze=freeze,
        source=" + ".join(["built-in", *[p.source for p in present]]),
        subagent_max=subagent_max,
        subagent_deny_types=subagent_deny_types,
        budget=Limits(lowest(b.session_usd for b in budgets), lowest(b.day_usd for b in budgets),
                      min([b.warn_at for b in budgets if b.any] or [0.8])),
        tools=tuple(r for p in present for r in p.tools),
    )


def tool_risk(policy: Policy, tool_name: str) -> str:
    """An MCP tool's risk: the riskiest matching rule's, else its verb's."""
    stated = [r.risk for r in policy.tools if r.risk and r.matches(tool_name)]
    if stated:
        return max(stated, key=MCP_RISKS.index)
    parts = mcp_parts(tool_name)
    return mcp_tool_risk(parts[1]) if parts else ""


def tool_ceiling(policy: Policy, tool_name: str) -> int:
    """How far this one tool may go, before its class's level and ceiling.
    Each matching rule allows its ``ceiling`` or its risk's; the lowest wins.
    With no rule, an MCP tool's verb decides; other tools are not limited here."""
    allowed = [r.ceiling if r.ceiling is not None else TOOL_CEILINGS[r.risk]
               for r in policy.tools if r.matches(tool_name) and (r.ceiling is not None or r.risk)]
    parts = mcp_parts(tool_name)
    if not allowed and parts:
        allowed = [TOOL_CEILINGS[mcp_tool_risk(parts[1])]]
    return min(allowed, default=2)


def ceiling(policy: Policy, key: str, tool_name: str) -> int:
    """The effective ceiling of one call: its class's and its tool's, the lower."""
    return min(policy.ceilings[key], tool_ceiling(policy, tool_name))


def tool_ask_reason(policy: Policy, tool_name: str) -> str:
    """Why a capped MCP tool asks, or "" when its tool is not what holds it back."""
    parts = mcp_parts(tool_name)
    if not parts or tool_ceiling(policy, tool_name) > 0:
        return ""
    if tool_risk(policy, tool_name) == "destructive":
        return f"{parts[1]} on {parts[0]} is destructive: it always asks."
    return f"{parts[1]} on {parts[0]} always asks in this repo (policy)."


def effective(conn: sqlite3.Connection, repo: str, root: str | Path) -> Policy:
    return merge(from_file(root), local(conn, ALL_REPOS), local(conn, repo))


def denied(policy: Policy, tool_name: str, tool_input: dict, root: str | Path) -> str:
    """Why this policy forbids the call, or an empty string."""
    for rule in policy.tools:
        if rule.forbidden and rule.matches(tool_name):
            return f"this repo's policy forbids the tool '{tool_name}' ({rule.pattern})"
    command = str(tool_input.get("command", ""))
    if command:
        low = command.lower()
        for rule in policy.deny_commands:
            r = rule.lower()
            if ("*" in r and fnmatch.fnmatch(low, r)) or ("*" not in r and r in low):
                return f"this repo's policy forbids '{rule}'"
        # Paths in a command: split it like a shell, and match each argument
        # as a path (normalised, traversal-proof) - never a raw substring.
        for token in _command_paths(command):
            for candidate in _path_forms(token, root):
                for pattern in policy.deny_paths:
                    if fnmatch.fnmatch(candidate, pattern):
                        return f"this repo's policy forbids touching '{pattern}'"
    path = str(tool_input.get("file_path", "") or "")
    if path:
        for candidate in _path_forms(path, root):
            for pattern in policy.deny_paths:
                if fnmatch.fnmatch(candidate, pattern):
                    return f"this repo's policy forbids editing '{pattern}'"
    return ""


def denied_subagent(policy: Policy, tool_name: str, tool_input: dict) -> str:
    """Why a requested subagent type is forbidden, or an empty string."""
    if str(tool_name).lower() not in {"agent", "task", "spawn_agent"}:
        return ""
    requested = str(tool_input.get("subagent_type") or tool_input.get("agent_type")
                    or tool_input.get("type") or "").strip()
    if not requested:
        return ""
    for denied_type in policy.subagent_deny_types:
        if fnmatch.fnmatch(requested.lower(), denied_type.lower()):
            return f"this repo's policy forbids spawning subagent type '{requested}'"
    return ""


_SHELL_PUNCTUATION = set("();<>|&")
_WRAPPERS = "`'\"$(){}"


def _command_paths(command: str) -> list[str]:
    """Arguments of a shell command that could name a file.

    Split like a shell *including* its operators, so a path glued to one
    (``echo hi>.env``, ``cat .env|less``, ``cat<.env``, ``(cat .env)``) is
    still its own word; then strip quotes, backticks and ``$(`` wrappers and
    unwrap ``key=value``. Options (``-x``) are not paths."""
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        words = list(lexer)
    except ValueError:
        words = command.split()
    out = []
    for word in words:
        # A word may still carry operators shlex kept inside it (e.g. after an
        # unbalanced quote): split on them too.
        for piece in _split_on(word, _SHELL_PUNCTUATION):
            piece = piece.strip(_WRAPPERS)
            if not piece:
                continue
            if piece.startswith("-"):
                # Options can carry a path: --file=.env, -var-file=x, -o.env.
                value = _option_value(piece)
                if value:
                    out.append(value.strip(_WRAPPERS))
                continue
            out.append(piece.split("=", 1)[-1] if "=" in piece and not piece.startswith(("./", "/", "..")) else piece)
    return [w for w in out if w]


def _option_value(option: str) -> str:
    """The value glued to an option, if any: ``--file=.env`` / ``-var-file=x``
    -> after ``=``; ``-o.env`` (single-letter option with its value attached)
    -> ``.env``. A bare flag (``-v``, ``--force``) has none."""
    if "=" in option:
        return option.split("=", 1)[1]
    if len(option) > 2 and option[1] != "-" and option[1].isalpha():
        return option[2:]
    return ""


def _split_on(word: str, chars: set[str]) -> list[str]:
    parts, current = [], ""
    for ch in word:
        if ch in chars:
            parts.append(current)
            current = ""
        else:
            current += ch
    parts.append(current)
    return parts


def _path_forms(path: str, root: str | Path) -> list[str]:
    """Every form a deny pattern is matched against. The path is always
    normalised first (``..`` resolved against the repo root), so traversal
    cannot dodge a rule. Inside the repo: the repo-relative path and its file
    name. Outside it (e.g. ``../../other-repo/.env``): every trailing part of
    the absolute path, so ``.env`` or ``infra/prod/**`` still match."""
    raw = Path(path)
    base = Path(root)
    target = raw if raw.is_absolute() else base / raw
    norm = Path(os.path.normpath(str(target)))
    try:
        norm = norm.resolve()
        rel = norm.relative_to(base.resolve())
        parts = rel.parts
        return [Path(*parts).as_posix(), parts[-1]] if parts else []
    except (ValueError, OSError):
        parts = [p for p in norm.as_posix().split("/") if p and not p.endswith(":")]
        return ["/".join(parts[i:]) for i in range(len(parts))]


def write_starter(root: str | Path) -> Path:
    path = Path(root) / POLICY_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(STARTER, encoding="utf-8")
    return path
