"""Tickets repository - the agent's inbox of customer messages."""

from __future__ import annotations

import json
import sqlite3


def insert(
    conn: sqlite3.Connection, *, source: str, body: str, sender: str | None = None, subject: str | None = None
) -> int:
    """Store a new customer message. The caller commits."""
    cur = conn.execute(
        "INSERT INTO tickets (source, sender, subject, body) VALUES (?, ?, ?, ?)",
        (source, (sender or "").strip() or None, (subject or "").strip() or None, body.strip()),
    )
    return int(cur.lastrowid)


def get(conn: sqlite3.Connection, ticket_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()


def open_question(
    conn: sqlite3.Connection, sender: str, *, exclude_id: int | None = None, days: int = 14
) -> sqlite3.Row | None:
    """The latest message from this sender where the agent asked the customer
    something (status needs_info) that has not been answered yet."""
    return conn.execute(
        """
        SELECT * FROM tickets
         WHERE status = 'needs_info' AND lower(sender) = lower(?) AND id != ?
           AND handled_at >= datetime('now', ?)
         ORDER BY id DESC LIMIT 1
        """,
        (sender.strip(), exclude_id or 0, f"-{days} days"),
    ).fetchone()


def mark_answered(conn: sqlite3.Connection, ticket_id: int, by_ticket_id: int | None) -> None:
    """The customer answered the agent's question; the conversation continues
    in a later message. The caller commits."""
    where = f" in message #{by_ticket_id}" if by_ticket_id else ""
    conn.execute(
        "UPDATE tickets SET status = 'answered', outcome = ? WHERE id = ? AND status = 'needs_info'",
        (f"The customer replied; the agent continued{where}.", ticket_id),
    )


def list_new(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM tickets WHERE status = 'new' ORDER BY id").fetchall()


def list_recent(conn: sqlite3.Connection, limit: int = 60) -> list[dict]:
    rows = conn.execute("SELECT * FROM tickets ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    out = []
    for row in rows:
        item = dict(row)
        item["steps"] = json.loads(item.get("steps") or "[]")
        out.append(item)
    return out


def record_outcome(conn: sqlite3.Connection, ticket_id: int, outcome) -> None:
    """Store what the agent did with a message. The caller commits."""
    conn.execute(
        """
        UPDATE tickets
           SET status = ?, outcome = ?, reply = ?, steps = ?, run_id = ?, trace_id = ?,
               follows_ticket_id = COALESCE(?, follows_ticket_id), handled_at = datetime('now')
         WHERE id = ?
        """,
        (outcome.status, outcome.summary, outcome.reply, outcome.steps_json(),
         outcome.run_id, outcome.trace_id, outcome.follows_ticket_id, ticket_id),
    )
    if outcome.follows_ticket_id:
        mark_answered(conn, outcome.follows_ticket_id, ticket_id)
