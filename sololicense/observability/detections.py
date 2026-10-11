"""Custom detection rules.

These are the load-bearing checks that make autonomy *earned*: each one, when
it fires, demotes the task class. They are pure functions over observed facts
so they can be unit-tested and so the same logic both (a) emits a neatlogs
detection event and (b) is mirrored as a local rule - the documented mapping
when a live neatlogs key is absent.

Three rules, matching the spec:
    state_mismatch        the DB side effect did not match what was intended
    missing_verification  the agent reported done without reading the result back
    policy_breach         the attempted action exceeded the current license
"""

from __future__ import annotations

from dataclasses import dataclass

from sololicense.domain.license import Decision

CRITICAL = "critical"
WARNING = "warning"

# Decisions that actually touch the world.
_EXECUTING = (Decision.AUTO_EXECUTE, Decision.AUTO_EXECUTE_AUDITED)


@dataclass(frozen=True)
class Detection:
    rule: str
    severity: str
    message: str


def detect_state_mismatch(
    *, intended_delta: float, actual_delta: float, verified: bool = True
) -> Detection | None:
    """Fire when the verified change in ``refunded_amount`` does not equal the
    refund the agent intended to make (the signature of a quiet failure)."""
    if not verified:
        return None
    if abs(intended_delta - actual_delta) > 1e-9:
        return Detection(
            rule="state_mismatch",
            severity=CRITICAL,
            message=(
                f"Intended change ${intended_delta:.2f} but the system of record moved "
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
            message="Execution reported complete without reading the result back.",
        )
    return None


def detect_duplicate_action(*, duplicate: bool) -> Detection | None:
    """Fire when a retry tries to execute an already-executed action key."""
    if duplicate:
        return Detection(
            rule="duplicate_action",
            severity=CRITICAL,
            message="Idempotency key already executed; duplicate action blocked.",
        )
    return None


def detect_policy_breach(
    *, authorized: Decision, attempted: Decision
) -> Detection | None:
    """Fire when the agent executed beyond what the license authorised.

    The authorised decision already folds in level, amount, and the L2 ceiling
    (see :func:`sololicense.domain.license.decide`), so the rule is simply:
    the agent executed while the license said suggest or draft only.
    """
    if attempted in _EXECUTING and authorized not in _EXECUTING:
        return Detection(
            rule="policy_breach",
            severity=CRITICAL,
            message=(
                f"Agent attempted {attempted.name} but the license only "
                f"authorised {authorized.name}."
            ),
        )
    return None
