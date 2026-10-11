from __future__ import annotations

from dataclasses import replace

import pytest

from sololicense.agent.tools import execute_refund
from sololicense.db.repositories import orders as orders_repo
from sololicense.domain.license import Decision
from sololicense.security import Actor, Role
from sololicense.services.policy_gate import PermitRejected, PolicyGate
from sololicense.services.policy_service import PolicyService


ADMIN = Actor("admin:permit-test", Role.ADMIN)


def _refund_permit(harness):
    policy = PolicyService(harness.conn, harness.config).ensure_default_policy()
    return PolicyGate(harness.conn).issue(
        policy=policy,
        task_class="refund",
        tool="refund",
        order_id="ORD-1001",
        amount=10,
        authorized=Decision.AUTO_EXECUTE,
        attempted=Decision.AUTO_EXECUTE,
        license_level=2,
        approved=False,
        actor=ADMIN,
    )


def test_consumed_permit_cannot_write_twice(harness):
    """A replayed authorization must not create a second customer side effect."""
    permit = _refund_permit(harness)
    execute_refund(
        harness.conn, order_id="ORD-1001", amount=10, suppress_write=False,
        permit=permit, column="refunded_amount",
    )

    with pytest.raises(PermitRejected, match="already used"):
        execute_refund(
            harness.conn, order_id="ORD-1001", amount=10, suppress_write=False,
            permit=permit, column="refunded_amount",
        )


def test_permit_rejects_a_different_amount_before_the_write(harness):
    """A permit cannot be widened by changing the tool call payload."""
    permit = _refund_permit(harness)
    before = harness.conn.execute(
        "SELECT refunded_amount FROM orders WHERE order_id = 'ORD-1001'"
    ).fetchone()["refunded_amount"]

    with pytest.raises(PermitRejected, match="does not match"):
        execute_refund(
            harness.conn, order_id="ORD-1001", amount=20, suppress_write=False,
            permit=permit, column="refunded_amount",
        )

    after = harness.conn.execute(
        "SELECT refunded_amount FROM orders WHERE order_id = 'ORD-1001'"
    ).fetchone()["refunded_amount"]
    assert after == before


def test_order_write_boundary_rejects_a_missing_execution_permit(harness):
    """No alternate repository caller can write an agent side effect unauthorised."""
    before = orders_repo.get_refunded_amount(harness.conn, "ORD-1001")

    with pytest.raises(PermissionError, match="execution permit"):
        orders_repo.apply_effect(
            harness.conn, "ORD-1001", "refunded_amount", 10, permit=None
        )

    assert orders_repo.get_refunded_amount(harness.conn, "ORD-1001") == before
