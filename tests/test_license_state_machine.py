"""Unit tests for the pure autonomy state machine."""

from __future__ import annotations

import pytest

from sololicense.domain.license import (
    Decision,
    LicenseLevel,
    LicenseState,
    decide,
    demote_on_detection,
    record_clean_run,
    restore,
)

CEILING = 50.0


def test_effective_level_is_l0_when_quarantined():
    state = LicenseState("refund", level=LicenseLevel.L3, quarantined=True)
    assert state.effective_level is LicenseLevel.L0


@pytest.mark.parametrize(
    "level, amount, expected",
    [
        (LicenseLevel.L0, 10, Decision.SUGGEST),
        (LicenseLevel.L1, 10, Decision.DRAFT_FOR_APPROVAL),
        (LicenseLevel.L2, 10, Decision.AUTO_EXECUTE),
        (LicenseLevel.L2, 999, Decision.DRAFT_FOR_APPROVAL),  # above ceiling
        (LicenseLevel.L3, 999, Decision.AUTO_EXECUTE_AUDITED),
    ],
)
def test_decide_matches_the_ladder(level, amount, expected):
    state = LicenseState("refund", level=level)
    assert decide(state, amount, l2_ceiling=CEILING) is expected


def test_quarantined_state_only_ever_suggests():
    state = LicenseState("refund", level=LicenseLevel.L3, quarantined=True)
    assert decide(state, 10, l2_ceiling=CEILING) is Decision.SUGGEST


def test_negative_amount_rejected():
    with pytest.raises(ValueError):
        decide(LicenseState("refund"), -1, l2_ceiling=CEILING)


def test_clean_runs_promote_after_threshold():
    state = LicenseState("refund", level=LicenseLevel.L2)
    state = record_clean_run(state, promotion_threshold=3)
    state = record_clean_run(state, promotion_threshold=3)
    assert state.level is LicenseLevel.L2 and state.consecutive_clean_runs == 2
    state = record_clean_run(state, promotion_threshold=3)
    assert state.level is LicenseLevel.L3 and state.consecutive_clean_runs == 0


def test_promotion_stops_at_l3():
    state = LicenseState("refund", level=LicenseLevel.L3, consecutive_clean_runs=2)
    state = record_clean_run(state, promotion_threshold=3)
    assert state.level is LicenseLevel.L3


def test_quarantined_class_earns_no_credit():
    state = LicenseState("refund", level=LicenseLevel.L0, quarantined=True)
    assert record_clean_run(state, promotion_threshold=3) == state


def test_detection_crashes_to_l0_and_quarantines():
    state = LicenseState("refund", level=LicenseLevel.L3, consecutive_clean_runs=2)
    demoted = demote_on_detection(state)
    assert demoted.level is LicenseLevel.L0
    assert demoted.quarantined is True
    assert demoted.consecutive_clean_runs == 0
    assert demoted.demoted_from is LicenseLevel.L3


def test_redetecting_remembers_original_fall_height():
    state = demote_on_detection(LicenseState("refund", level=LicenseLevel.L2))
    again = demote_on_detection(state)
    assert again.demoted_from is LicenseLevel.L2


def test_restore_clears_quarantine_to_chosen_level():
    state = demote_on_detection(LicenseState("refund", level=LicenseLevel.L3))
    restored = restore(state, LicenseLevel.L1)
    assert restored.level is LicenseLevel.L1
    assert restored.quarantined is False
    assert restored.demoted_from is None
