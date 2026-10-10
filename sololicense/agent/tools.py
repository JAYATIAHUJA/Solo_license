"""Tools the refund worker can call.

Deliberately, ``execute_refund`` reports success even when a fault suppressed
the write. That models the real hazard the whole project is about: a tool's
response is not proof of a side effect. Only :mod:`sololicense.services.
verification` — which reads SQLite back — is trusted."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from sololicense.db.repositories import orders as orders_repo


@dataclass(frozen=True)
class ToolResult:
    """What a tool claims happened. Treated as a claim, never as evidence."""

    ok: bool
    message: str


def execute_refund(
    conn: sqlite3.Connection,
    *,
    order_id: str,
    amount: float,
    suppress_write: bool,
) -> ToolResult:
    """Attempt to refund ``amount`` against ``order_id``.

    When ``suppress_write`` is set (quiet-failure fault) the database is left
    untouched but the tool still returns ``ok=True`` — exactly the lie the
    verifier is there to catch. The caller commits on a real write.
    """
    if suppress_write:
        return ToolResult(ok=True, message="Refund processed (reported).")

    orders_repo.apply_refund(conn, order_id, amount)
    return ToolResult(ok=True, message="Refund processed.")
