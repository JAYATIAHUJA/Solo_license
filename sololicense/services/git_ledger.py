"""Git-backed license ledger.

Every autonomy change (promote / demote / restore) appends one line to
``ledger/license_ledger.jsonl`` and commits *only that file*. The commit is the
Entire-compatible checkpoint: its history is the graph of how a task class
earned and lost its license, and each message explains the change.

Commits are scoped to the ledger file so running the app never sweeps up
unrelated working-tree edits. If git is unavailable the ledger line is still
written and the caller simply gets ``None`` for the sha — the app keeps working.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_LEDGER_RELPATH = Path("ledger") / "license_ledger.jsonl"


@dataclass(frozen=True)
class LedgerEntry:
    task_class: str
    kind: str          # promote | demote | restore
    from_level: int
    to_level: int
    reason: str
    run_id: int | None
    trace_id: str | None


def _commit_message(entry: LedgerEntry) -> str:
    """Human- and Entire-readable message describing one license change."""
    verb = {
        "promote": "promote",
        "demote": "demote",
        "restore": "restore",
    }.get(entry.kind, entry.kind)
    title = (
        f"license({entry.task_class}): {verb} L{entry.from_level}"
        f" -> L{entry.to_level}"
    )
    body = [title, "", entry.reason]
    if entry.run_id is not None:
        body.append(f"run: {entry.run_id}")
    if entry.trace_id:
        body.append(f"trace: {entry.trace_id}")
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

    def _run_git(self, args: list[str]) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git", *args],
            cwd=self._repo_root,
            capture_output=True,
            text=True,
            check=False,
        )

    def _ensure_repo(self) -> None:
        self._repo_root.mkdir(parents=True, exist_ok=True)
        if not (self._repo_root / ".git").exists():
            self._run_git(["init", "-q"])
        self._run_git(["config", "user.name", "Solo License"])
        self._run_git(["config", "user.email", "solo-license@example.invalid"])

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
        self._ensure_repo()
        rel = _LEDGER_RELPATH.as_posix()
        add = self._run_git(["add", "--", rel])
        if add.returncode != 0:
            return None
        commit = self._run_git(["commit", "-m", _commit_message(entry), "--", rel])
        if commit.returncode != 0:
            return None
        sha = self._run_git(["rev-parse", "--short", "HEAD"])
        return sha.stdout.strip() or None
