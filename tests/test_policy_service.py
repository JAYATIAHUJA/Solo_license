from __future__ import annotations

import sqlite3
from dataclasses import replace

import pytest
from sololicense.domain.license import LicenseLevel
from sololicense.domain.models import RefundRequest, RunStatus
from sololicense.domain.policy import PolicyRule
from sololicense.security import Actor, Role
from sololicense.services.policy_service import PolicyService


ADMIN = Actor("admin:policy-test", Role.ADMIN)


def _rules(service: PolicyService, *, refund_ceiling: float = 50.0):
    active = service.ensure_default_policy()
    return tuple(
        replace(rule, l2_ceiling=refund_ceiling)
        if rule.task_class == "refund"
        else rule
        for rule in active.rules
    )


def test_default_policy_uses_existing_refund_and_credit_settings(harness):
    """A first policy preserves the safety values a workspace already uses."""
    service = PolicyService(harness.conn, harness.config)

    policy = service.ensure_default_policy()

    assert policy.version == 1
    assert policy.rule_for("refund").l2_ceiling == 50
    assert policy.rule_for("store_credit").l2_ceiling == 75
    assert policy.rule_for("refund").minimum_samples == 3


def test_activation_creates_immutable_next_version(harness):
    """Changing a policy creates v2 without rewriting the policy that ran v1."""
    service = PolicyService(harness.conn, harness.config)
    v1 = service.ensure_default_policy()

    v2 = service.activate(
        name="Tighter refund ceiling",
        summary="Require approval for larger refunds.",
        rules=_rules(service, refund_ceiling=25),
        actor=ADMIN,
    )

    assert v2.version == 2
    assert service.get(v1.version).rule_for("refund").l2_ceiling == 50
    assert v2.rule_for("refund").l2_ceiling == 25


def test_new_policy_does_not_count_outcomes_from_previous_version(harness):
    """A policy change starts a fresh evidence window instead of borrowing trust."""
    service = PolicyService(harness.conn, harness.config)
    service.ensure_default_policy()
    service.activate(
        name="New evidence window",
        summary="Require evidence under new terms.",
        rules=_rules(service),
        actor=ADMIN,
    )

    progress = service.evaluation_for("refund")

    assert progress.sample_size == 0
    assert progress.eligible is False


def test_activation_preview_holds_class_for_review_when_evidence_is_missing(harness):
    """A strict policy change records review work; it never silently promotes."""
    service = PolicyService(harness.conn, harness.config)
    service.ensure_default_policy()

    impacts = service.preview_activation(_rules(service))

    refund = next(impact for impact in impacts if impact.task_class == "refund")
    assert refund.action == "hold_for_review"
    assert "3" in refund.reason


def test_clean_evidence_and_promotion_are_scoped_to_the_run_policy(harness):
    """Policy v2 begins a new evidence window even after v1 promoted a class."""
    service = PolicyService(harness.conn, harness.config)
    v1 = service.ensure_default_policy()

    for _ in range(3):
        harness.worker.run_refund(RefundRequest("ORD-1001", "Ada", 10.0, "late"))

    assert harness.license_service.get_or_create("refund").level is LicenseLevel.L3
    recorded_versions = harness.conn.execute(
        "SELECT DISTINCT policy_version FROM runs WHERE task_class = 'refund'"
    ).fetchall()
    assert [row["policy_version"] for row in recorded_versions] == [v1.version]

    v2 = service.activate(
        name="New evidence terms",
        summary="Require fresh clean runs before another promotion.",
        rules=_rules(service),
        actor=ADMIN,
    )
    harness.license_service.restore_license(
        "refund", LicenseLevel.L2, reason="testing policy-specific evidence", actor=ADMIN
    )
    harness.worker.run_refund(RefundRequest("ORD-1001", "Ada", 10.0, "late"))

    state = harness.license_service.get_or_create("refund")
    assert state.level is LicenseLevel.L2
    assert state.consecutive_clean_runs == 1
    assert service.evaluation_for("refund", policy=v2).sample_size == 1


def test_active_policy_ceiling_controls_future_l2_authorization(harness):
    """A policy edit changes the next run's boundary, not only its display."""
    service = PolicyService(harness.conn, harness.config)
    service.ensure_default_policy()
    v2 = service.activate(
        name="Tighter execution boundary",
        summary="Require human approval over five dollars.",
        rules=_rules(service, refund_ceiling=5),
        actor=ADMIN,
    )

    result = harness.worker.run_refund(RefundRequest("ORD-1001", "Ada", 10.0, "late"))

    assert result.status is RunStatus.PENDING_APPROVAL
    row = harness.conn.execute("SELECT policy_version FROM runs WHERE id = ?", (result.run_id,)).fetchone()
    assert row["policy_version"] == v2.version


def test_policy_approval_boundary_can_hold_an_l2_action_for_review(harness):
    """The per-policy approval rule is enforced as well as stored."""
    service = PolicyService(harness.conn, harness.config)
    active = service.ensure_default_policy()
    strict_rules = tuple(
        replace(rule, requires_approval_at_or_above=3)
        if rule.task_class == "refund" else rule
        for rule in active.rules
    )
    service.activate(
        name="Approval through L2",
        summary="Refunds require approval until L3.",
        rules=strict_rules,
        actor=ADMIN,
    )

    result = harness.worker.run_refund(RefundRequest("ORD-1001", "Ada", 10.0, "late"))

    assert result.status is RunStatus.PENDING_APPROVAL


def test_policy_rules_and_impacts_cannot_be_mutated_after_creation(harness):
    """SQLite itself, not just the API, preserves audit history."""
    service = PolicyService(harness.conn, harness.config)
    active = service.ensure_default_policy()
    v2 = service.activate(
        name="Immutable audit check", summary="Test policy persistence.",
        rules=_rules(service), actor=ADMIN,
    )

    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        harness.conn.execute("UPDATE policy_rules SET l2_ceiling = 999 WHERE policy_id = ?", (v2.id,))
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        harness.conn.execute("UPDATE policy_impacts SET action = 'eligible' WHERE next_version = ?", (v2.version,))
    assert service.get(active.version).rule_for("refund").l2_ceiling == 50
