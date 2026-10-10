"""Integration tests for the end-to-end refund loop."""

from __future__ import annotations

import subprocess

from sololicense.db.repositories import license as license_repo
from sololicense.db.repositories import orders as orders_repo
from sololicense.domain.license import LicenseLevel
from sololicense.domain.models import FaultMode, RefundRequest, RunStatus


def _dial(harness):
    return license_repo.get_state(harness.conn, "refund")


def _git_log(repo) -> str:
    return subprocess.run(
        ["git", "log", "--oneline"], cwd=repo, capture_output=True, text=True
    ).stdout


def test_clean_runs_execute_verify_and_promote(harness):
    for _ in range(harness.config.promotion_clean_runs):
        result = harness.worker.run_refund(
            RefundRequest("ORD-1001", "Ada", 25.0, "defective")
        )
        assert result.status is RunStatus.CLEAN
        assert result.actual_delta == 25.0

    assert _dial(harness).level is LicenseLevel.L3
    # Side effect is real and verifiable in SQLite.
    assert orders_repo.get_refunded_amount(harness.conn, "ORD-1001") == 75.0
    assert "promote" in _git_log(harness.repo)


def test_quiet_failure_demotes_and_leaves_db_untouched(harness):
    harness.fault_injector.arm("refund", FaultMode.QUIET_FAILURE)
    result = harness.worker.run_refund(
        RefundRequest("ORD-1002", "Grace", 40.0, "late")
    )

    assert result.status is RunStatus.DEMOTED
    assert any(d.rule == "state_mismatch" for d in result.detections)
    assert _dial(harness).level is LicenseLevel.L0
    assert _dial(harness).quarantined is True
    # The quiet failure really did not move the ledger.
    assert orders_repo.get_refunded_amount(harness.conn, "ORD-1002") == 0.0
    assert "demote" in _git_log(harness.repo)


def test_policy_violation_above_ceiling_demotes(harness):
    harness.fault_injector.arm("refund", FaultMode.POLICY_VIOLATION)
    result = harness.worker.run_refund(
        RefundRequest("ORD-1004", "Katherine", 120.0, "big")
    )

    assert result.status is RunStatus.DEMOTED
    assert any(d.rule == "policy_breach" for d in result.detections)
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


def test_custom_task_class_is_persisted_on_run(harness):
    result = harness.worker.run_refund(
        RefundRequest("ORD-1001", "Ada", 25.0, "defective"),
        task_class="vip_refund",
        approved=True,
    )

    row = harness.conn.execute(
        "SELECT task_class FROM runs WHERE id = ?", (result.run_id,)
    ).fetchone()
    assert row["task_class"] == "vip_refund"


def test_fault_stays_armed_through_a_run_that_does_not_execute(harness):
    harness.fault_injector.arm("refund", FaultMode.QUIET_FAILURE)

    held = harness.worker.run_refund(RefundRequest("ORD-1004", "Kat", 120.0, "over ceiling"))
    assert held.status is RunStatus.PENDING_APPROVAL
    assert harness.fault_injector.peek("refund") is FaultMode.QUIET_FAILURE

    caught = harness.worker.run_refund(RefundRequest("ORD-1001", "Ada", 25.0, "defective"))
    assert caught.status is RunStatus.DEMOTED
    assert harness.fault_injector.peek("refund") is FaultMode.NONE
