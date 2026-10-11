"""Integration tests for the end-to-end refund loop."""

from __future__ import annotations

import json
import subprocess
from dataclasses import replace

import pytest

from sololicense.db.repositories import license as license_repo
from sololicense.db.repositories import orders as orders_repo
from sololicense.domain.license import LicenseLevel
from sololicense.domain.models import FaultMode, RefundRequest, RunStatus
from sololicense.security import Actor, Role


def _dial(harness):
    return license_repo.get_state(harness.conn, "refund")


def _git_log(repo) -> str:
    return subprocess.run(
        ["git", "log", "--oneline"], cwd=repo, capture_output=True, text=True
    ).stdout


def test_clean_runs_execute_verify_and_promote(harness):
    # Promotion needs the policy's three clean results and an economic bound
    # below break-even; a long verified record makes the bound hold here.
    license_repo.upsert_state(
        harness.conn, replace(_dial(harness), level=LicenseLevel.L2, successes=100_000)
    )
    harness.conn.commit()
    for order_id, amount in (("ORD-1001", 25.0), ("ORD-1003", 15.0), ("ORD-1005", 45.0)):
        result = harness.worker.run_refund(RefundRequest(order_id, "x", amount, "defective"))
        assert result.status is RunStatus.CLEAN
        assert result.actual_delta == amount

    assert _dial(harness).level is LicenseLevel.L3
    # Side effects are real and verifiable in SQLite.
    assert orders_repo.get_refunded_amount(harness.conn, "ORD-1001") == 25.0
    assert "promote" in _git_log(harness.repo)


def test_quiet_failure_is_caught_recovered_and_still_demotes(harness):
    harness.fault_injector.arm("refund", FaultMode.QUIET_FAILURE)
    result = harness.worker.run_refund(
        RefundRequest("ORD-1002", "Grace", 40.0, "late")
    )

    # The tool lied: the read-back caught it and the licence paused ...
    assert result.status is RunStatus.DEMOTED
    assert any(d.rule == "state_mismatch" for d in result.detections)
    assert _dial(harness).level is LicenseLevel.L0
    assert _dial(harness).quarantined is True
    assert _dial(harness).failures == 1
    # ... and the agent recovered the customer's refund with one safe retry.
    assert result.recovered is True
    assert orders_repo.get_refunded_amount(harness.conn, "ORD-1002") == 40.0
    spans = [r["name"] for r in harness.conn.execute(
        "SELECT name FROM spans WHERE run_id = ? ORDER BY id", (result.run_id,))]
    assert spans.index("recover.reconcile") < spans.index("recover.retry") < spans.index("recover.done")
    assert "demote" in _git_log(harness.repo)


def test_retry_uses_the_same_idempotency_key(harness):
    harness.fault_injector.arm("refund", FaultMode.QUIET_FAILURE)
    result = harness.worker.run_refund(
        RefundRequest("ORD-1003", "Alan", 15.0, "x"), idempotency_key="k-1"
    )
    keys = [
        json.loads(r["attributes"]).get("idempotency_key")
        for r in harness.conn.execute(
            "SELECT attributes FROM spans WHERE run_id = ? AND name IN ('tool.execute_refund', 'recover.retry')",
            (result.run_id,),
        )
    ]
    assert keys == ["k-1", "k-1"]


def test_policy_violation_above_ceiling_demotes(harness):
    harness.fault_injector.arm("refund", FaultMode.POLICY_VIOLATION)
    before = orders_repo.get_refunded_amount(harness.conn, "ORD-1004")
    result = harness.worker.run_refund(
        RefundRequest("ORD-1004", "Katherine", 120.0, "big")
    )

    assert result.status is RunStatus.DEMOTED
    assert any(d.rule == "policy_breach" for d in result.detections)
    assert orders_repo.get_refunded_amount(harness.conn, "ORD-1004") == before
    assert _dial(harness).level is LicenseLevel.L0


def test_quarantined_runs_only_suggest_and_earn_no_credit(harness):
    harness.fault_injector.arm("refund", FaultMode.QUIET_FAILURE)
    harness.worker.run_refund(RefundRequest("ORD-1002", "Grace", 40.0, "late"))
    assert _dial(harness).quarantined is True

    result = harness.worker.run_refund(
        RefundRequest("ORD-1003", "Alan", 15.0, "x")
    )
    assert result.status is RunStatus.SUGGESTED
    assert _dial(harness).level is LicenseLevel.L0
    assert _dial(harness).consecutive_clean_runs == 0


def test_restore_lifts_quarantine_to_chosen_level(harness):
    harness.fault_injector.arm("refund", FaultMode.QUIET_FAILURE)
    harness.worker.run_refund(RefundRequest("ORD-1002", "Grace", 40.0, "late"))

    harness.license_service.restore_license(
        "refund", LicenseLevel.L2, reason="evidence reviewed"
    )
    assert _dial(harness).level is LicenseLevel.L2
    assert _dial(harness).quarantined is False
    assert "restore" in _git_log(harness.repo)


def test_store_credit_class_verifies_its_own_column(harness):
    result = harness.worker.run_refund(
        RefundRequest("ORD-1001", "Ada", 10.0, "late delivery"),
        task_class="store_credit",
        approved=True,
    )

    row = harness.conn.execute(
        "SELECT task_class FROM runs WHERE id = ?", (result.run_id,)
    ).fetchone()
    assert row["task_class"] == "store_credit"
    assert result.status is RunStatus.CLEAN
    assert orders_repo.get_effect_amount(harness.conn, "ORD-1001", "credit_issued") == 10.0
    assert orders_repo.get_refunded_amount(harness.conn, "ORD-1001") == 0.0


def test_store_credit_ladder_is_independent_of_refund(harness):
    harness.fault_injector.arm("refund", FaultMode.QUIET_FAILURE)
    caught = harness.worker.run_refund(RefundRequest("ORD-1001", "Ada", 25.0, "x"))
    assert caught.status is RunStatus.DEMOTED

    credit = harness.license_service.get_or_create("store_credit")
    assert credit.quarantined is False


def test_unknown_task_class_is_rejected(harness):
    with pytest.raises(ValueError, match="Unknown task class"):
        harness.worker.run_refund(
            RefundRequest("ORD-1001", "Ada", 25.0, "x"), task_class="vip_refund"
        )


def test_fault_stays_armed_through_a_run_that_does_not_execute(harness):
    harness.fault_injector.arm("refund", FaultMode.QUIET_FAILURE)

    held = harness.worker.run_refund(RefundRequest("ORD-1004", "Kat", 120.0, "over ceiling"))
    assert held.status is RunStatus.PENDING_APPROVAL
    assert harness.fault_injector.peek("refund") is FaultMode.QUIET_FAILURE

    caught = harness.worker.run_refund(RefundRequest("ORD-1001", "Ada", 25.0, "defective"))
    assert caught.status is RunStatus.DEMOTED
    assert harness.fault_injector.peek("refund") is FaultMode.NONE


def test_skip_verification_demotes_with_missing_verification_only(harness):
    harness.fault_injector.arm("refund", FaultMode.SKIP_VERIFICATION)

    result = harness.worker.run_refund(
        RefundRequest("ORD-1001", "Ada", 25.0, "defective")
    )

    assert result.status is RunStatus.DEMOTED
    assert [d.rule for d in result.detections] == ["missing_verification"]
    assert orders_repo.get_refunded_amount(harness.conn, "ORD-1001") == 25.0
    assert _dial(harness).level is LicenseLevel.L0


def test_fault_mode_is_recorded_only_when_consumed(harness):
    harness.fault_injector.arm("refund", FaultMode.QUIET_FAILURE)

    held = harness.worker.run_refund(RefundRequest("ORD-1004", "Kat", 120.0, "over ceiling"))
    held_row = harness.conn.execute(
        "SELECT fault_mode FROM runs WHERE id = ?", (held.run_id,)
    ).fetchone()
    assert held_row["fault_mode"] == FaultMode.NONE.value

    consumed = harness.worker.run_refund(RefundRequest("ORD-1001", "Ada", 25.0, "defective"))
    consumed_row = harness.conn.execute(
        "SELECT fault_mode FROM runs WHERE id = ?", (consumed.run_id,)
    ).fetchone()
    assert consumed_row["fault_mode"] == FaultMode.QUIET_FAILURE.value


def test_duplicate_idempotency_key_demotes_without_double_refund(harness):
    first = harness.worker.run_refund(
        RefundRequest("ORD-1001", "Ada", 25.0, "defective"),
        idempotency_key="msg-ord-1001-25",
    )
    assert first.status is RunStatus.CLEAN

    retry = harness.worker.run_refund(
        RefundRequest("ORD-1001", "Ada", 25.0, "defective"),
        idempotency_key="msg-ord-1001-25",
    )

    assert retry.status is RunStatus.DEMOTED
    assert [d.rule for d in retry.detections] == ["duplicate_action"]
    assert orders_repo.get_refunded_amount(harness.conn, "ORD-1001") == 25.0


def test_run_and_demotion_event_record_the_initiating_actor(harness):
    harness.fault_injector.arm("refund", FaultMode.QUIET_FAILURE)

    result = harness.worker.run_refund(
        RefundRequest("ORD-1001", "Ada Lovelace", 25.0, "refund"),
        actor=Actor("ops-17", Role.OPERATOR),
    )

    run = harness.conn.execute("SELECT * FROM runs WHERE id = ?", (result.run_id,)).fetchone()
    event = harness.conn.execute("SELECT * FROM license_events ORDER BY id DESC LIMIT 1").fetchone()
    assert run["actor_id"] == "ops-17"
    assert run["actor_role"] == "operator"
    assert event["actor_id"] == "ops-17"
    assert event["actor_role"] == "operator"
