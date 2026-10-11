"""Side-effect verification.

The one rule the whole system is built on: a tool's return value is never
evidence that something happened. To know whether a refund landed we read the
amount back from the system of record - Stripe, or the local store - through
the order's connector, and compare the measured change with what was intended."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VerificationResult:
    """Outcome of reading a side effect back from the system of record."""

    before: float
    after: float
    intended_delta: float
    verified: bool  # True once a read-back was actually performed

    @property
    def actual_delta(self) -> float:
        return round(self.after - self.before, 2)

    @property
    def matched(self) -> bool:
        """Did the measured change equal the intended change (to the cent)?"""
        return abs(self.actual_delta - self.intended_delta) < 0.005


def verify(*, before: float, after: float, intended_delta: float) -> VerificationResult:
    """Compare a read-back with what was intended."""
    return VerificationResult(before=before, after=after, intended_delta=intended_delta, verified=True)


def unverified(*, before: float, intended_delta: float) -> VerificationResult:
    """An execution whose read-back did not run or complete."""
    return VerificationResult(before=before, after=before, intended_delta=intended_delta, verified=False)
