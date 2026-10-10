"""License-events repository — the git-backed ledger of every autonomy change.

Each row pairs with a git commit (``git_sha``) so Entire can graph and explain
the full history of how a task class earned or lost its license."""

from __future__ import annotations

import sqlite3


def insert_event(
    conn: sqlite3.Connection,
    *,
    task_class: str,
    kind: str,
    from_level: int,
    to_level: int,
    reason: str,
    run_id: int | None,
) -> int:
    """Persist a license event (git_sha filled in later). Caller commits."""
    cur = conn.execute(
        """
        INSERT INTO license_events
            (task_class, kind, from_level, to_level, reason, run_id)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (task_class, kind, from_level, to_level, reason, run_id),
    )
    return int(cur.lastrowid)


def set_git_sha(conn: sqlite3.Connection, event_id: int, git_sha: str) -> None:
    """Link an event to its git commit. The caller commits."""
    conn.execute(
        "UPDATE license_events SET git_sha = ? WHERE id = ?",
        (git_sha, event_id),
    )


def list_events(
    conn: sqlite3.Connection, task_class: str | None = None, limit: int = 50
) -> list[sqlite3.Row]:
    if task_class is None:
        return conn.execute(
            "SELECT * FROM license_events ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return conn.execute(
        """
        SELECT * FROM license_events
         WHERE task_class = ? ORDER BY id DESC LIMIT ?
        """,
        (task_class, limit),
    ).fetchall()
