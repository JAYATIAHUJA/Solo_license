"""The autonomy ladder and its state machine.

A *task class* (e.g. ``refund``) holds one :class:`LicenseState`. The agent may
only do what the current level permits. Levels are *earned* from verified
evidence — enough successes that the failure rate is provably below the
break-even rate of the operator's own economics (see
:mod:`sololicense.domain.trust`) — and *lost* immediately when a detection fires.

    L0  suggest only                       (human does everything)
    L1  draft + human approves each run
    L2  auto-execute under a dollar ceiling
    L3  full auto, post-hoc audit

Design notes
------------
* This module is pure: given the same inputs it always returns the same
  outputs and never touches a database, clock, or network. Persistence and
  side effects live in outer layers.
* A detection demotes the class straight to ``L0`` *and* quarantines it.
  While quarantined the class behaves at L0 and **cannot** auto-promote —
  only a human-reviewed evidence packet (``restore``) clears the quarantine.
  This is what makes recovery "with judgment, not blind retry".
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import IntEnum

from sololicense.domain.trust import TrustLadder


class LicenseLevel(IntEnum):
    """Rungs on the autonomy ladder. Ordered, so comparisons are meaningful."""

    L0 = 0  # suggest only
    L1 = 1  # draft + human approve
    L2 = 2  # auto under a threshold
    L3 = 3  # full auto with post-hoc audit

    @property
    def label(self) -> str:
        return {
            LicenseLevel.L0: "Suggest only",
            LicenseLevel.L1: "Draft + approve",
            LicenseLevel.L2: "Auto under ceiling",
            LicenseLevel.L3: "Full auto (audited)",
        }[self]


class Decision(IntEnum):
    """What the agent is permitted to do with a specific refund request."""

    SUGGEST = 0            # produce a recommendation only; no execution
    DRAFT_FOR_APPROVAL = 1  # prepare the change; a human must approve it
    AUTO_EXECUTE = 2        # execute now within policy
    AUTO_EXECUTE_AUDITED = 3  # execute now, flagged for post-hoc audit


@dataclass(frozen=True)
class LicenseState:
    """Immutable snapshot of one task class's standing on the ladder.

    Instances are never mutated in place; every transition returns a new
    state, which keeps the state machine easy to reason about and test.
    """

    task_class: str
    level: LicenseLevel = LicenseLevel.L0
    # Verified successes since the last rung change (shown as a streak).
    consecutive_clean_runs: int = 0
    quarantined: bool = False
    # Level the class held before the most recent detection demotion, so a
    # reviewer can see "it fell from L2" when deciding how far to restore.
    demoted_from: LicenseLevel | None = None
    # Lifetime evidence. Never reset: a job type that failed before needs
    # more successes to climb again.
    successes: int = 0
    failures: int = 0

    @property
    def effective_level(self) -> LicenseLevel:
        """Level actually in force. A quarantined class always acts at L0."""
        return LicenseLevel.L0 if self.quarantined else self.level


def decide(
    state: LicenseState,
    amount: float,
    *,
    l2_ceiling: float,
) -> Decision:
    """Resolve what the agent may do for a refund of ``amount`` dollars.

    This is the single authority on permissions. The worker must route every
    request through it and must never execute a side effect the returned
    :class:`Decision` does not authorise.
    """
    if amount < 0:
        raise ValueError("refund amount cannot be negative")

    level = state.effective_level

    if level is LicenseLevel.L0:
        return Decision.SUGGEST
    if level is LicenseLevel.L1:
        return Decision.DRAFT_FOR_APPROVAL
    if level is LicenseLevel.L2:
        # Auto only under the ceiling; anything above falls back to approval.
        if amount <= l2_ceiling:
            return Decision.AUTO_EXECUTE
        return Decision.DRAFT_FOR_APPROVAL
    return Decision.AUTO_EXECUTE_AUDITED  # L3


def record_clean_run(state: LicenseState, *, ladder: TrustLadder) -> LicenseState:
    """Add one verified success and promote one rung if the evidence now
    proves the failure rate is below the next step's break-even rate.

    A quarantined class accrues no credit — it must be restored by a human
    first.
    """
    if state.quarantined:
        return state

    credited = replace(
        state,
        successes=state.successes + 1,
        consecutive_clean_runs=state.consecutive_clean_runs + 1,
        demoted_from=None,
    )
    if state.level < LicenseLevel.L3 and ladder.step(int(state.level)).earned(
        credited.successes, credited.failures
    ):
        return replace(credited, level=LicenseLevel(state.level + 1), consecutive_clean_runs=0)
    return credited


def record_rejection(state: LicenseState) -> LicenseState:
    """A person rejected what the agent proposed: one failure of evidence.
    The class was already supervised, so the level does not change."""
    return replace(state, failures=state.failures + 1, consecutive_clean_runs=0)


def demote_on_detection(state: LicenseState) -> LicenseState:
    """Crash the class to L0 and quarantine it. Called the instant a
    detection fires. Idempotent in spirit: re-detecting a quarantined class
    keeps it quarantined and remembers the highest level it fell from."""
    fell_from = state.demoted_from if state.quarantined else state.level
    return replace(
        state,
        level=LicenseLevel.L0,
        consecutive_clean_runs=0,
        quarantined=True,
        demoted_from=fell_from,
        failures=state.failures + 1,
    )


def restore(state: LicenseState, target: LicenseLevel) -> LicenseState:
    """Lift the quarantine and set the class to a human-chosen level.

    Only ever called after a reviewer has read the evidence packet, so the
    judgement lives with the human; this function just applies the decision.
    """
    return replace(
        state,
        level=target,
        consecutive_clean_runs=0,
        quarantined=False,
        demoted_from=None,
    )
