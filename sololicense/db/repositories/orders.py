"""Orders repository — the agent's "real world".

``refunded_amount`` is the authoritative side effect: the verifier reads it
back after every execution. Nothing else in the system is allowed to claim a
refund happened."""

from __future__ import annotations

import sqlite3


def get_order(conn: sqlite3.Connection, order_id: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM orders WHERE order_id = ?", (order_id,)
    ).fetchone()


def get_refunded_amount(conn: sqlite3.Connection, order_id: str) -> float:
    """Authoritative verified refund for an order (0 if unknown)."""
    return get_effect_amount(conn, order_id, "refunded_amount")


def apply_refund(conn: sqlite3.Connection, order_id: str, amount: float) -> None:
    """Persist a real refund side effect. The caller commits."""
    apply_effect(conn, order_id, "refunded_amount", amount)


def remaining_balance(row: sqlite3.Row) -> float:
    """What can still be paid out on an order across every task class."""
    keys = row.keys()
    credit = float(row["credit_issued"]) if "credit_issued" in keys else 0.0
    return round(float(row["amount"]) - float(row["refunded_amount"]) - credit, 2)


def get_effect_amount(conn: sqlite3.Connection, order_id: str, column: str) -> float:
    """Authoritative verified side effect in ``column`` (0 if unknown)."""
    _check_column(column)
    row = conn.execute(
        f"SELECT {column} FROM orders WHERE order_id = ?", (order_id,)
    ).fetchone()
    return float(row[column]) if row else 0.0


def apply_effect(conn: sqlite3.Connection, order_id: str, column: str, amount: float) -> None:
    """Persist a real side effect into ``column``. The caller commits."""
    _check_column(column)
    status = "refunded" if column == "refunded_amount" else "credited"
    cur = conn.execute(
        f"""
        UPDATE orders
           SET {column} = {column} + ?,
               status = ?,
               updated_at = datetime('now')
         WHERE order_id = ?
        """,
        (amount, status, order_id),
    )
    if cur.rowcount != 1:
        raise KeyError(f"unknown order_id: {order_id!r}")


_EFFECT_COLUMNS = frozenset({"refunded_amount", "credit_issued"})


def _check_column(column: str) -> None:
    # Column names come from the task-class registry, never from a request;
    # the allow-list keeps the f-string SQL above safe regardless.
    if column not in _EFFECT_COLUMNS:
        raise ValueError(f"not a side-effect column: {column!r}")


def list_orders(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM orders ORDER BY order_id"
    ).fetchall()
