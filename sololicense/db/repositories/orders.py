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


def upsert_orders(conn: sqlite3.Connection, records) -> tuple[int, int]:
    """Insert new orders and refresh known ones from a connector.

    Returns ``(added, updated)``. Side-effect columns are only taken from a
    connector that is itself the system of record (Stripe); an imported CSV
    never overwrites what the agent has already paid out. The caller commits.
    """
    added = updated = 0
    for r in records:
        existing = get_order(conn, r.order_id)
        if existing is None:
            conn.execute(
                """
                INSERT INTO orders (order_id, customer, amount, refunded_amount, credit_issued,
                                    status, email, ordered_at, currency, source, external_id, customer_ref)
                VALUES (?, ?, ?, ?, ?, 'paid', ?, ?, ?, ?, ?, ?)
                """,
                (r.order_id, r.customer, round(r.amount, 2), r.refunded_amount, r.credit_issued,
                 r.email, r.ordered_at, r.currency, r.source, r.external_id, r.customer_ref),
            )
            added += 1
            continue
        if existing["source"] != r.source and existing["source"] != "manual":
            continue  # never let one connector overwrite another's order
        effects = (
            ", refunded_amount = :refunded_amount, credit_issued = MAX(credit_issued, :credit_issued)"
            if r.source == "stripe" else ""
        )
        conn.execute(
            f"""
            UPDATE orders SET customer = :customer, amount = :amount, email = :email,
                   ordered_at = :ordered_at, currency = :currency, source = :source,
                   external_id = :external_id, customer_ref = :customer_ref,
                   updated_at = datetime('now'){effects}
             WHERE order_id = :order_id
            """,
            {**r.__dict__, "amount": round(r.amount, 2)},
        )
        updated += 1
    return added, updated


def set_effect_amount(conn: sqlite3.Connection, order_id: str, column: str, value: float) -> None:
    """Cache an amount read back from an external system of record. The caller commits."""
    _check_column(column)
    conn.execute(
        f"UPDATE orders SET {column} = ?, updated_at = datetime('now') WHERE order_id = ?",
        (round(value, 2), order_id),
    )


def find_by_email(conn: sqlite3.Connection, email: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM orders WHERE lower(email) = lower(?) ORDER BY ordered_at DESC, order_id DESC",
        (email.strip(),),
    ).fetchall()
