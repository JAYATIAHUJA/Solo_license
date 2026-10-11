"""Digest-only persistence for single-use execution capabilities."""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import sqlite3

from sololicense.domain.models import ExecutionPermit


def create(conn: sqlite3.Connection, permit: ExecutionPermit, *, actor_id: str) -> None:
    conn.execute(
        """
        INSERT INTO execution_permits
            (permit_digest, policy_version, task_class, tool, order_id, amount, actor_id, expires_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            _digest(permit.token), permit.policy_version, permit.task_class, permit.tool,
            permit.order_id, permit.amount, actor_id, permit.expires_at.isoformat(),
        ),
    )


def consume(conn: sqlite3.Connection, permit: ExecutionPermit) -> str | None:
    """Atomically consume an exact, unexpired permit or return a safe reason."""
    now = datetime.now(timezone.utc).isoformat()
    cur = conn.execute(
        """
        UPDATE execution_permits
           SET consumed_at = ?, disposition = 'consumed'
         WHERE permit_digest = ? AND policy_version = ? AND task_class = ?
           AND tool = ? AND order_id = ? AND amount = ?
           AND consumed_at IS NULL AND expires_at > ?
        """,
        (now, _digest(permit.token), permit.policy_version, permit.task_class,
         permit.tool, permit.order_id, permit.amount, now),
    )
    if cur.rowcount == 1:
        return None
    row = conn.execute(
        "SELECT consumed_at, expires_at FROM execution_permits WHERE permit_digest = ?",
        (_digest(permit.token),),
    ).fetchone()
    if row is None:
        return "unknown"
    if row["consumed_at"] is not None:
        return "already used"
    if row["expires_at"] <= now:
        return "expired"
    return "does not match this tool call"


def _digest(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()
