"""Side-effect verification.

The one rule the whole system is built on: a tool's return value is never
evidence that something happened. To know whether a refund landed we read
``orders.refunded_amount`` back out of SQLite and compare the measured change
to what was intended."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from sololicense.db.repositories import orders as orders_repo


@dataclass(frozen=True)
class VerificationResult:
    """Outcome of reading a side effect back from the database."""

    before: float
    after: float
    intended_delta: float
    verified: bool  # True once a read-back was actually performed

    @property
    def actual_delta(self) -> float:
        return round(self.after - self.before, 2)

    @property
    def matched(self) -> bool:
        """Did the measured change equal the intended change?"""
        return abs(self.actual_delta - self.intended_delta) <= 1e-9


def read_refunded(conn: sqlite3.Connection, order_id: str) -> float:
    """Snapshot the authoritative refunded amount for an order."""
    return orders_repo.get_refunded_amount(conn, order_id)


def verify_refund(
    conn: sqlite3.Connection,
    *,
    order_id: str,
    before: float,
    intended_delta: float,
) -> VerificationResult:
    """Read the side effect back and compare it to what was intended."""
    after = read_refunded(conn, order_id)
    return VerificationResult(
        before=before,
        after=after,
        intended_delta=intended_delta,
        verified=True,
    )
