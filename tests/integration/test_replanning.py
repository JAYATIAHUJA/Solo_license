"""Visible re-planning: every lookup strategy and every recovery decision is a
span with a reason, so a trace shows what the agent tried and why it changed course."""

from __future__ import annotations

import json

from sololicense.domain.license import LicenseLevel
from sololicense.domain.models import FaultMode


def _spans(harness, trace_id: str) -> list[tuple[str, dict]]:
    rows = harness.conn.execute(
        "SELECT name, attributes FROM spans WHERE trace_id = ? ORDER BY id", (trace_id,)
    ).fetchall()
    return [(r["name"], json.loads(r["attributes"] or "{}")) for r in rows]


def _attempts(harness, trace_id: str) -> list[dict]:
    return [a for name, a in _spans(harness, trace_id) if name == "agent.find_order.attempt"]


def _permits(harness, order_id: str) -> int:
    return harness.conn.execute(
        "SELECT COUNT(*) FROM execution_permits WHERE order_id = ?", (order_id,)
    ).fetchone()[0]


def test_order_number_lookup_is_one_attempt(harness):
    out = harness.agent.handle("ORD-1001 arrived broken, refund please", sender="ada@example.com")

    attempts = _attempts(harness, out.trace_id)
    assert [(a["strategy"], a["result"]) for a in attempts] == [("order_number", "found")]


def test_unknown_order_number_falls_back_to_the_sender_email(harness):
    out = harness.agent.handle("Refund ORD-9999 please", sender="alan@example.com")

    attempts = _attempts(harness, out.trace_id)
    assert [(a["strategy"], a["result"]) for a in attempts] == [
        ("order_number", "not_found"), ("sender_email", "found"),
    ]
    assert out.order_id == "ORD-1003"


def test_ambiguous_email_lookup_is_recorded_before_asking(harness):
    harness.conn.execute(
        "INSERT INTO orders (order_id, customer, amount, refunded_amount, status, email, ordered_at, source)"
        " VALUES ('ORD-1010', 'Ada Lovelace', 20.0, 0, 'paid', 'ada@example.com', date('now'), 'sample')"
    )
    harness.conn.commit()

    out = harness.agent.handle("Can I get my money back?", sender="ada@example.com")

    attempts = _attempts(harness, out.trace_id)
    assert [(a["strategy"], a["result"]) for a in attempts] == [("sender_email", "ambiguous")]
    assert attempts[0]["candidates"] == 2


def test_failed_verification_records_a_reason_coded_replan(harness):
    harness.fault_injector.arm("refund", FaultMode.QUIET_FAILURE)

    out = harness.agent.handle("ORD-1002 refund please", sender="grace@example.com")

    spans = _spans(harness, out.trace_id)
    names = [n for n, _ in spans]
    replan = next(a for n, a in spans if n == "recover.replan")
    assert replan["reason_code"] == "no_change"
    assert replan["next_action"] == "retry_same_key"
    assert names.index("recover.reconcile") < names.index("recover.replan") < names.index("recover.retry")
    step = next(s for s in out.steps if s.name == "replan")
    assert "no change" in step.detail.lower()


def test_recovery_uses_exactly_one_retry_permit_and_a_resubmission_none(harness):
    harness.fault_injector.arm("refund", FaultMode.QUIET_FAILURE)
    out = harness.agent.handle("ORD-1002 refund please", sender="grace@example.com", idempotency_key="ticket:x")
    assert out.run.recovered
    assert _permits(harness, "ORD-1002") == 2   # the first attempt and one retry

    # Restored, so only the idempotency key (not quarantine) can stop a second write.
    harness.license_service.restore_license("refund", LicenseLevel.L2, reason="reviewed")
    harness.agent.handle("ORD-1002 refund please", sender="grace@example.com", idempotency_key="ticket:x")

    assert _permits(harness, "ORD-1002") == 2
