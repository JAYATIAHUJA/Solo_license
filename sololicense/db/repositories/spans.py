"""Spans repository — a local mirror of observability spans so the evidence
packet and before/after comparison work even without a neatlogs key."""

from __future__ import annotations

import json
import sqlite3


def insert_span(
    conn: sqlite3.Connection,
    *,
    trace_id: str,
    run_id: int | None,
    name: str,
    attributes: dict,
    status: str = "ok",
) -> int:
    """Persist one span. The caller commits."""
    cur = conn.execute(
        """
        INSERT INTO spans (trace_id, run_id, name, attributes, status)
        VALUES (?, ?, ?, ?, ?)
        """,
        (trace_id, run_id, name, json.dumps(attributes), status),
    )
    return int(cur.lastrowid)


def list_for_trace(conn: sqlite3.Connection, trace_id: str) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM spans WHERE trace_id = ? ORDER BY id", (trace_id,)
    ).fetchall()
    return [
        {
            "name": r["name"],
            "status": r["status"],
            "attributes": json.loads(r["attributes"]),
            "created_at": r["created_at"],
        }
        for r in rows
    ]
