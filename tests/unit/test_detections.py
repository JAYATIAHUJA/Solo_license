"""Unit tests for the custom detection rules."""

from __future__ import annotations

from sololicense.domain.license import Decision
from sololicense.observability.detections import (
    detect_duplicate_action,
    detect_missing_verification,
    detect_policy_breach,
    detect_state_mismatch,
)


def test_state_mismatch_fires_on_quiet_failure():
    hit = detect_state_mismatch(intended_delta=40.0, actual_delta=0.0)
    assert hit is not None and hit.rule == "state_mismatch"


def test_state_mismatch_silent_when_side_effect_matches():
    assert detect_state_mismatch(intended_delta=25.0, actual_delta=25.0) is None


def test_missing_verification_fires_when_not_verified():
    hit = detect_missing_verification(verified=False)
    assert hit is not None and hit.rule == "missing_verification"


def test_missing_verification_silent_when_verified():
    assert detect_missing_verification(verified=True) is None


def test_duplicate_action_fires_for_previously_executed_key():
    hit = detect_duplicate_action(duplicate=True)
    assert hit is not None and hit.rule == "duplicate_action"


def test_duplicate_action_silent_for_new_key():
    assert detect_duplicate_action(duplicate=False) is None


def test_policy_breach_fires_when_executing_beyond_authorization():
    hit = detect_policy_breach(
        authorized=Decision.DRAFT_FOR_APPROVAL, attempted=Decision.AUTO_EXECUTE
    )
    assert hit is not None and hit.rule == "policy_breach"


def test_policy_breach_silent_when_within_authorization():
    assert (
        detect_policy_breach(
            authorized=Decision.AUTO_EXECUTE, attempted=Decision.AUTO_EXECUTE
        )
        is None
    )


def test_policy_breach_silent_for_non_executing_attempt():
    assert (
        detect_policy_breach(
            authorized=Decision.SUGGEST, attempted=Decision.DRAFT_FOR_APPROVAL
        )
        is None
    )
