"""Risk-calibrated trust math."""

import math

import pytest

from sololicense.domain.trust import (
    TrustPolicy,
    beta_cdf,
    break_even_rate,
    failure_upper_bound,
    runs_needed,
)


def test_beta_cdf_matches_closed_forms():
    # Beta(1, b): CDF = 1 - (1 - x)^b ; Beta(a, 1): CDF = x^a
    assert beta_cdf(0.1, 1, 10) == pytest.approx(1 - 0.9 ** 10)
    assert beta_cdf(0.7, 3, 1) == pytest.approx(0.7 ** 3)
    assert beta_cdf(0.5, 4, 4) == pytest.approx(0.5)
    assert beta_cdf(0.0, 2, 2) == 0.0 and beta_cdf(1.0, 2, 2) == 1.0


def test_upper_bound_with_no_failures_has_closed_form():
    # Beta(1, 1 + s) quantile: 1 - (1 - c)^(1 / (s + 1))
    for s in (0, 5, 40):
        assert failure_upper_bound(s, 0, 0.9) == pytest.approx(1 - 0.1 ** (1 / (s + 1)), abs=1e-9)


def test_failures_widen_the_bound():
    assert failure_upper_bound(50, 3, 0.9) > failure_upper_bound(50, 0, 0.9)


def test_break_even_comes_from_the_economics():
    assert break_even_rate(1.875, 120) == pytest.approx(0.015625)
    assert break_even_rate(5, 0) == 1.0


def test_runs_needed_is_the_first_count_that_earns():
    policy = TrustPolicy(review_cost_saved=1.875, incident_cost=120, confidence=0.9)
    n = policy.runs_needed(0, 0)
    assert n == math.ceil(math.log(0.1) / math.log(1 - policy.target_rate)) - 1
    assert policy.earned(n, 0) and not policy.earned(n - 1, 0)
    assert runs_needed(10, 0, 0.0, 0.9) is None


def test_a_failure_means_more_evidence_is_needed():
    policy = TrustPolicy(review_cost_saved=2.0, incident_cost=20, confidence=0.9)
    assert policy.runs_needed(0, 1) > policy.runs_needed(0, 0)
