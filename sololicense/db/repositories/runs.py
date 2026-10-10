"""Runs repository — the recent-runs feed and the before/after numbers that
make a neatlogs trace comparison concrete."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True)
class NewRun:
    """Everything needed to persist one completed run."""

    task_class: str
    order_id: str
    requested_amount: float
    level_at_run: int
    decision: str
    status: str
    executed: bool
    before_refunded: float
    after_refunded: float
    idempotency_key: str | None
    fault_mode: str
    trace_id: str | None
    notes: str | None


def insert_run(conn: sqlite3.Connection, run: NewRun) -> int:
    """Persist a run and return its id. The caller commits."""
    cur = conn.execute(
        """
        INSERT INTO runs
            (task_class, order_id, requested_amount, level_at_run, decision,
             status, executed, before_refunded, after_refunded, idempotency_key,
             fault_mode, trace_id, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run.task_class,
            run.order_id,
            run.requested_amount,
            run.level_at_run,
            run.decision,
            run.status,
            1 if run.executed else 0,
            run.before_refunded,
            run.after_refunded,
            run.idempotency_key,
            run.fault_mode,
            run.trace_id,
            run.notes,
        ),
    )
    return int(cur.lastrowid)


def get_run(conn: sqlite3.Connection, run_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()


def get_executed_by_idempotency_key(
    conn: sqlite3.Connection, key: str
) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT * FROM runs
         WHERE idempotency_key = ?
           AND executed = 1
         ORDER BY id DESC
         LIMIT 1
        """,
        (key,),
    ).fetchone()


def list_recent(conn: sqlite3.Connection, limit: int = 20) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM runs ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
