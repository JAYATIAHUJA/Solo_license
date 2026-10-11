"""Detections repository - rule firings surfaced as incidents in the UI."""

from __future__ import annotations

import sqlite3


def insert_detection(
    conn: sqlite3.Connection,
    *,
    run_id: int,
    rule: str,
    severity: str,
    message: str,
    trace_id: str | None,
) -> int:
    """Persist one detection and return its id. The caller commits."""
    cur = conn.execute(
        """
        INSERT INTO detections (run_id, rule, severity, message, trace_id)
        VALUES (?, ?, ?, ?, ?)
        """,
        (run_id, rule, severity, message, trace_id),
    )
    return int(cur.lastrowid)


def list_for_run(conn: sqlite3.Connection, run_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM detections WHERE run_id = ? ORDER BY id", (run_id,)
    ).fetchall()


def list_recent(conn: sqlite3.Connection, limit: int = 20) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM detections ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
