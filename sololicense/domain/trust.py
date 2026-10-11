"""Risk-calibrated trust — how much evidence an agent needs before it may act alone.

A fixed rule such as "three clean runs in a row" ignores two things that decide
whether autonomy is worth it: how *sure* we are about the agent's failure rate,
and how *expensive* one of its mistakes is compared with a human check. This
module replaces the fixed count with a small amount of Bayesian arithmetic.

* Every verified outcome is evidence. With a uniform prior, the failure rate of
  a job type after ``s`` verified successes and ``f`` verified failures follows
  ``Beta(1 + f, 1 + s)``.
* Autonomy pays when the expected cost of letting the agent act alone is lower
  than the review it replaces: ``p_fail * incident_cost < review_cost_saved``.
  That gives a **break-even failure rate** — computed from the operator's own
  economics, never hard-coded.
* A job type earns the next level only when the *upper credible bound* of its
  failure rate (at the operator's confidence) is below that break-even rate.
  One failure widens the bound, so a job type that slipped once needs more
  evidence to climb again.

Everything here is pure: no I/O, no clock, deterministic.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# Above this many additional runs we report "not reachable" rather than a number.
MAX_RUNS_SEARCH = 100_000


def _log_binom(n: int, k: int) -> float:
    return math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1)


def beta_cdf(x: float, a: int, b: int) -> float:
    """Regularised incomplete beta ``I_x(a, b)`` for integer ``a, b >= 1``.

    Uses the exact identity with the binomial tail:
    ``I_x(a, b) = P(Binomial(a + b - 1, x) >= a)``.
    """
    if a < 1 or b < 1:
        raise ValueError("beta_cdf needs integer parameters >= 1")
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    n = a + b - 1
    log_x, log_1x = math.log(x), math.log1p(-x)

    def tail(lo: int, hi: int) -> float:
        terms = [_log_binom(n, j) + j * log_x + (n - j) * log_1x for j in range(lo, hi + 1)]
        peak = max(terms)
        return math.exp(peak) * sum(math.exp(t - peak) for t in terms)

    # Sum whichever side of the binomial has fewer terms.
    if a <= b:
        return max(0.0, min(1.0, 1.0 - tail(0, a - 1)))
    return max(0.0, min(1.0, tail(a, n)))


def failure_upper_bound(successes: int, failures: int, confidence: float) -> float:
    """Upper credible bound on the failure rate: the ``confidence`` quantile
    of ``Beta(1 + failures, 1 + successes)``. Bisection keeps it dependency-free."""
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence must be strictly between 0 and 1")
    a, b = 1 + max(0, failures), 1 + max(0, successes)
    lo, hi = 0.0, 1.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if beta_cdf(mid, a, b) < confidence:
            lo = mid
        else:
            hi = mid
    return hi


def break_even_rate(review_cost_saved: float, incident_cost: float) -> float:
    """Highest failure rate at which acting alone is still cheaper than a review."""
    if incident_cost <= 0:
        return 1.0
    return max(0.0, min(1.0, review_cost_saved / incident_cost))


def runs_needed(successes: int, failures: int, target_rate: float, confidence: float) -> int | None:
    """Additional verified successes (with no new failure) before the upper bound
    drops to ``target_rate``. ``0`` means already earned; ``None`` means out of reach."""
    if target_rate <= 0:
        return None
    if failure_upper_bound(successes, failures, confidence) <= target_rate:
        return 0
    # The bound falls monotonically with each success: exponential then binary search.
    step = 1
    while failure_upper_bound(successes + step, failures, confidence) > target_rate:
        step *= 2
        if step > MAX_RUNS_SEARCH:
            return None
    lo, hi = step // 2, step
    while lo + 1 < hi:
        mid = (lo + hi) // 2
        if failure_upper_bound(successes + mid, failures, confidence) <= target_rate:
            hi = mid
        else:
            lo = mid
    return hi


@dataclass(frozen=True)
class TrustPolicy:
    """The operator's economics, turned into a promotion rule.

    ``review_cost_saved`` is what one step up the ladder saves per action;
    ``incident_cost`` is what one unattended mistake costs; ``confidence`` is
    how sure the operator wants to be before letting go.
    """

    review_cost_saved: float
    incident_cost: float
    confidence: float = 0.9

    @property
    def target_rate(self) -> float:
        return break_even_rate(self.review_cost_saved, self.incident_cost)

    def earned(self, successes: int, failures: int) -> bool:
        """Upper credible bound <= break-even, i.e. P(p_fail <= target) >= confidence."""
        return beta_cdf(self.target_rate, 1 + max(0, failures), 1 + max(0, successes)) >= self.confidence

    def runs_needed(self, successes: int, failures: int) -> int | None:
        return runs_needed(successes, failures, self.target_rate, self.confidence)
