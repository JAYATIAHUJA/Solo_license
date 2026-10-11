"""Server-side authorization gate for tool execution."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import secrets
import sqlite3

from sololicense.db.repositories import permits
from sololicense.domain.license import Decision
from sololicense.domain.models import BlockedPermit, ExecutionPermit
from sololicense.domain.policy import PolicyVersion
from sololicense.security import Actor


_EXECUTING = {Decision.AUTO_EXECUTE, Decision.AUTO_EXECUTE_AUDITED}


class PermitRejected(ValueError):
    """A tool received an absent, stale, replayed, or mismatched permit."""


class PolicyGate:
    def __init__(self, conn: sqlite3.Connection, *, ttl_seconds: int = 60) -> None:
        self._conn = conn
        self._ttl_seconds = ttl_seconds

    def issue(
        self, *, policy: PolicyVersion, task_class: str, tool: str, order_id: str,
        amount: float, authorized: Decision, attempted: Decision, license_level: int,
        approved: bool, actor: Actor,
    ) -> ExecutionPermit | BlockedPermit:
        if attempted not in _EXECUTING:
            return BlockedPermit("The attempted decision does not execute a tool.")
        if authorized not in _EXECUTING:
            return BlockedPermit("The license did not authorize this execution.")
        rule = policy.rule_for(task_class)
        if rule.allowed_tool != tool:
            return BlockedPermit("The active policy does not allow this tool for the task class.")
        if not approved and license_level < rule.requires_approval_at_or_above:
            return BlockedPermit("The active policy requires human approval at this license level.")
        if amount < 0:
            return BlockedPermit("The requested amount is invalid.")
        permit = ExecutionPermit(
            token=secrets.token_urlsafe(32), policy_version=policy.version,
            task_class=task_class, tool=tool, order_id=order_id, amount=amount,
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=self._ttl_seconds),
        )
        permit_id = permits.create(self._conn, permit, actor_id=actor.actor_id)
        return replace(permit, id=permit_id)

    def consume_for_write(self, permit: ExecutionPermit) -> None:
        reason = permits.consume(self._conn, permit)
        if reason is not None:
            raise PermitRejected(f"Execution permit {reason}.")
