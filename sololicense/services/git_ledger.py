"""Git-backed license ledger.

Every autonomy change (promote / demote / restore) appends one line to
``ledger/license_ledger.jsonl`` inside the configured ledger repository
(``SOLO_LEDGER_REPO``: ``.`` commits into this project so Entire can explain
the history; the default is a separate local repo) and commits *only that
file*. The commit is the
Entire-compatible checkpoint: its history is the graph of how a task class
earned and lost its license, and each message explains the change.

Commits are scoped to the ledger file so running the app never sweeps up
unrelated working-tree edits. If git is unavailable the ledger line is still
written and the caller simply gets ``None`` for the sha - the app keeps working.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_LEDGER_RELPATH = Path("ledger") / "license_ledger.jsonl"
_GIT_TIMEOUT_SECONDS = 20


@dataclass(frozen=True)
class LedgerEntry:
    task_class: str
    kind: str          # promote | demote | restore
    from_level: int
    to_level: int
    reason: str
    run_id: int | None
    trace_id: str | None
    entire_checkpoint: str | None = None


def _commit_message(entry: LedgerEntry) -> str:
    """Human- and Entire-readable message describing one license change."""
    verb = {
        "promote": "promote",
        "demote": "demote",
        "restore": "restore",
    }.get(entry.kind, entry.kind)
    if entry.kind == "policy":
        title = f"policy({entry.task_class}): {entry.reason.splitlines()[0][:72]}"
    elif entry.kind == "flag":
        title = f"flag({entry.task_class}): L{entry.from_level} -> L{entry.to_level}"
    else:
        title = (
            f"license({entry.task_class}): {verb} L{entry.from_level}"
            f" -> L{entry.to_level}"
        )
    body = [title, "", entry.reason]
    if entry.run_id is not None:
        body.append(f"run: {entry.run_id}")
    if entry.trace_id:
        body.append(f"trace: {entry.trace_id}")
    if entry.entire_checkpoint:
        body.append(f"agent checkpoint: entire checkpoint explain {entry.entire_checkpoint[:12]}")
    return "\n".join(body)


class GitLedger:
    """Appends to and commits the license ledger file.

    ``repo_root`` defaults to this repository; tests point it at a throwaway
    git repo so committing is exercised without touching project history."""

    def __init__(self, repo_root: Path = _REPO_ROOT) -> None:
        self._repo_root = repo_root
        self._ledger_file = repo_root / _LEDGER_RELPATH

    def record(self, entry: LedgerEntry) -> str | None:
        """Append the entry and commit the ledger file. Returns the short sha,
        or ``None`` if git is unavailable or nothing needed committing."""
        self._append(entry)
        return self._commit(entry)

    def _run_git(
        self, args: list[str], env: dict[str, str] | None = None
    ) -> subprocess.CompletedProcess:
        try:
            return subprocess.run(
                ["git", *args],
                cwd=self._repo_root,
                capture_output=True,
                text=True,
                check=False,
                env=env,
                timeout=_GIT_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            # A stuck git (lock, hook, network credential prompt) must never
            # freeze the agent: the ledger line is already written.
            return subprocess.CompletedProcess(["git", *args], 124, "", "timeout")

    def _ensure_repo(self) -> None:
        self._repo_root.mkdir(parents=True, exist_ok=True)
        # Check for .git here, not `rev-parse`: a ledger repo nested inside the
        # project must get its own repository, never commit into the parent.
        if not (self._repo_root / ".git").exists():
            self._run_git(["init", "-q"])

    def _identity_args(self) -> list[str]:
        """Commit as the repository's configured identity (the operator); only
        a fresh ledger repo with no identity gets a service fallback. Never
        rewrites the repository's own git config."""
        args: list[str] = []
        if not self._run_git(["config", "user.name"]).stdout.strip():
            args += ["-c", "user.name=Solo License"]
        if not self._run_git(["config", "user.email"]).stdout.strip():
            args += ["-c", "user.email=solo-license@example.invalid"]
        return args

    def _append(self, entry: LedgerEntry) -> None:
        self._ledger_file.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "task_class": entry.task_class,
                "kind": entry.kind,
                "from_level": entry.from_level,
                "to_level": entry.to_level,
                "reason": entry.reason,
                "run_id": entry.run_id,
                "trace_id": entry.trace_id,
            }
        )
        with self._ledger_file.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    def _commit(self, entry: LedgerEntry) -> str | None:
        """Commit only the ledger file through a private index.

        The ledger may live in the same repository people are developing in.
        Using a throwaway index means a license change can never sweep up (or
        be swept into) someone's staged work, and skipping repository hooks
        keeps developer tooling from blocking or rewriting this machine-made
        record. The developer's real index is then synced for this one path."""
        self._ensure_repo()
        rel = _LEDGER_RELPATH.as_posix()
        with tempfile.TemporaryDirectory() as scratch:
            env = {**os.environ, "GIT_INDEX_FILE": str(Path(scratch) / "index")}
            has_head = self._run_git(["rev-parse", "--verify", "-q", "HEAD"]).returncode == 0
            if has_head and self._run_git(["read-tree", "HEAD"], env).returncode != 0:
                return None
            if self._run_git(["add", "--", rel], env).returncode != 0:
                return None
            commit = self._run_git(
                [*self._identity_args(), "-c", f"core.hooksPath={scratch}",
                 "commit", "-q", "-m", _commit_message(entry)],
                env,
            )
            if commit.returncode != 0:
                return None
        # Keep `git status` clean for the ledger path; best effort only.
        self._run_git(["reset", "-q", "--", rel])
        sha = self._run_git(["rev-parse", "--short", "HEAD"])
        return sha.stdout.strip() or None
