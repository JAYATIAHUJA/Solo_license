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

3. **This machine's settings** (the dashboard), for one repository or for
   all of them (``"*"``). They can only tighten: a ceiling is the lowest of
   all layers, deny rules add up, and any layer can freeze.

A policy never grants anything: it only lowers ceilings and adds denials.
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

from sololicense.coding.actions import ACTION_CLASSES

POLICY_FILE = Path(".solo-license") / "policy.toml"
ALL_REPOS = "*"

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
"""


@dataclass(frozen=True)
class Policy:
    """One layer of policy (or the merged, effective one)."""

    ceilings: dict[str, int] = field(default_factory=dict)
    deny_commands: tuple[str, ...] = ()
    deny_paths: tuple[str, ...] = ()
    freeze: bool = False
    source: str = "built-in"

    def to_json(self) -> dict:
        return {"ceilings": dict(self.ceilings), "deny_commands": list(self.deny_commands),
                "deny_paths": list(self.deny_paths), "freeze": self.freeze, "source": self.source}

    @property
    def digest(self) -> str:
        blob = json.dumps({k: v for k, v in self.to_json().items() if k != "source"}, sort_keys=True)
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
    return Policy(ceilings, commands, paths, bool(freeze.get("enabled", False)), source)


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
    policy = _clean(raw, "this machine")
    conn.execute(
        "INSERT INTO agent_policies (repo, body, updated_at) VALUES (?, ?, datetime('now')) "
        "ON CONFLICT (repo) DO UPDATE SET body = excluded.body, updated_at = excluded.updated_at",
        (repo, json.dumps({"classes": {k: {"max": v} for k, v in policy.ceilings.items()},
                           "deny": {"commands": list(policy.deny_commands), "paths": list(policy.deny_paths)},
                           "freeze": {"enabled": policy.freeze}})),
    )
    return policy


def merge(*layers: Policy | None) -> Policy:
    """The strictest combination of the given layers."""
    present = [p for p in layers if p is not None]
    ceilings = {key: spec.max_level for key, spec in ACTION_CLASSES.items()}
    for p in present:
        for key, level in p.ceilings.items():
            ceilings[key] = min(ceilings[key], level)
    freeze = any(p.freeze for p in present)
    if freeze:
        ceilings = {key: 0 for key in ceilings}
    return Policy(
        ceilings=ceilings,
        deny_commands=tuple(dict.fromkeys(c for p in present for c in p.deny_commands)),
        deny_paths=tuple(dict.fromkeys(x for p in present for x in p.deny_paths)),
        freeze=freeze,
        source=" + ".join(["built-in", *[p.source for p in present]]),
    )


def effective(conn: sqlite3.Connection, repo: str, root: str | Path) -> Policy:
    return merge(from_file(root), local(conn, ALL_REPOS), local(conn, repo))


def denied(policy: Policy, tool_name: str, tool_input: dict, root: str | Path) -> str:
    """Why this policy forbids the call, or an empty string."""
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


def _command_paths(command: str) -> list[str]:
    """Arguments of a shell command that could name a file: shell-split,
    options and operators dropped, ``key=value`` / redirections unwrapped."""
    try:
        words = shlex.split(command, posix=True)
    except ValueError:
        words = command.split()
    out = []
    for word in words:
        word = word.lstrip("<>").split("=", 1)[-1] if not word.startswith("-") else ""
        if word and word not in ("&&", "||", "|", ";", "&"):
            out.append(word)
    return out


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
