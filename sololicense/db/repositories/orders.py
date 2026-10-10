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
    """Authoritative verified side effect for an order (0 if unknown)."""
    row = conn.execute(
        "SELECT refunded_amount FROM orders WHERE order_id = ?", (order_id,)
    ).fetchone()
    return float(row["refunded_amount"]) if row else 0.0


def apply_refund(conn: sqlite3.Connection, order_id: str, amount: float) -> None:
    """Persist a real refund side effect. The caller commits.

    Raises if the order does not exist so a bug can never silently no-op.
    """
    cur = conn.execute(
        """
        UPDATE orders
           SET refunded_amount = refunded_amount + ?,
               status = 'refunded',
               updated_at = datetime('now')
         WHERE order_id = ?
        """,
        (amount, order_id),
    )
    if cur.rowcount != 1:
        raise KeyError(f"unknown order_id: {order_id!r}")


def list_orders(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM orders ORDER BY order_id"
    ).fetchall()
