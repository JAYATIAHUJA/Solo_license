"""Armed-faults repository - persists the fault queued for a task class's next
run so a Streamlit rerun cannot lose it."""

from __future__ import annotations

import sqlite3

from sololicense.domain.models import FaultMode


def arm(conn: sqlite3.Connection, task_class: str, mode: FaultMode) -> None:
    """Queue a fault (or clear it with ``FaultMode.NONE``). Caller commits."""
    conn.execute(
        """
        INSERT INTO armed_faults (task_class, mode, updated_at)
        VALUES (?, ?, datetime('now'))
        ON CONFLICT(task_class) DO UPDATE SET
            mode = excluded.mode, updated_at = excluded.updated_at
        """,
        (task_class, mode.value),
    )


def peek(conn: sqlite3.Connection, task_class: str) -> FaultMode:
    """Read the armed fault without clearing it."""
    row = conn.execute(
        "SELECT mode FROM armed_faults WHERE task_class = ?", (task_class,)
    ).fetchone()
    return FaultMode(row["mode"]) if row else FaultMode.NONE


def consume(conn: sqlite3.Connection, task_class: str) -> FaultMode:
    """Read and clear the armed fault in one step. Caller commits."""
    mode = peek(conn, task_class)
    if mode is not FaultMode.NONE:
        conn.execute(
            "UPDATE armed_faults SET mode = 'none', updated_at = datetime('now')"
            " WHERE task_class = ?",
            (task_class,),
        )
    return mode
