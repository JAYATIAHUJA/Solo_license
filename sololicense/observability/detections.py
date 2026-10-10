"""Custom detection rules.

These are the load-bearing checks that make autonomy *earned*: each one, when
it fires, demotes the task class. They are pure functions over observed facts
so they can be unit-tested and so the same logic both (a) emits a neatlogs
detection event and (b) is mirrored as a local rule — the documented mapping
when a live neatlogs key is absent.

Three rules, matching the spec:
    state_mismatch        the DB side effect did not match what was intended
    missing_verification  the agent reported done without reading SQLite back
    policy_breach         the attempted action exceeded the current license
"""

from __future__ import annotations

from dataclasses import dataclass

from sololicense.domain.license import Decision, LicenseLevel

CRITICAL = "critical"
WARNING = "warning"


@dataclass(frozen=True)
class Detection:
    rule: str
    severity: str
    message: str


def detect_state_mismatch(
    *, intended_delta: float, actual_delta: float
) -> Detection | None:
    """Fire when the verified change in ``refunded_amount`` does not equal the
    refund the agent intended to make (the signature of a quiet failure)."""
    if abs(intended_delta - actual_delta) > 1e-9:
        return Detection(
            rule="state_mismatch",
            severity=CRITICAL,
            message=(
                f"Intended refund delta ${intended_delta:.2f} but SQLite moved "
                f"${actual_delta:.2f}. Tool response cannot be trusted."
            ),
        )
    return None


def detect_missing_verification(*, verified: bool) -> Detection | None:
    """Fire when an execution completed but no read-back verification ran."""
    if not verified:
        return Detection(
            rule="missing_verification",
            severity=CRITICAL,
            message="Execution reported complete without verifying SQLite state.",
        )
    return None


def detect_policy_breach(
    *,
    decision: Decision,
    level: LicenseLevel,
    amount: float,
    l2_ceiling: float,
) -> Detection | None:
    """Fire when an auto-execution would exceed what the license permits:

    * auto-executing at L0/L1 (those levels never auto-execute), or
    * auto-executing above the L2 ceiling.
    """
    auto = decision in (Decision.AUTO_EXECUTE, Decision.AUTO_EXECUTE_AUDITED)
    if not auto:
        return None

    if level in (LicenseLevel.L0, LicenseLevel.L1):
        return Detection(
            rule="policy_breach",
            severity=CRITICAL,
            message=(
                f"Auto-execution attempted at {level.name}, which only permits "
                f"{'suggestions' if level is LicenseLevel.L0 else 'drafts'}."
            ),
        )
    if level is LicenseLevel.L2 and amount > l2_ceiling:
        return Detection(
            rule="policy_breach",
            severity=CRITICAL,
            message=(
                f"Auto-executed ${amount:.2f} above the L2 ceiling of "
                f"${l2_ceiling:.2f}."
            ),
        )
    return None
