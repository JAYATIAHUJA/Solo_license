"""Risk-calibrated trust math and the τ-bench replay."""

import math

import pytest

from sololicense.bench import taubench as tb
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


def _write(correct, guards=()):
    return tb.Write(tool="cancel_pending_order", correct=correct, guards=tuple(guards))


def test_replay_policies_on_a_synthetic_stream():
    writes = [_write(True)] * 40 + [_write(False)] * 5 + [_write(True)] * 40
    costs = tb.Costs(incident=120)
    full = tb.simulate("full_auto", writes, costs=costs)
    assert full.harmful == 5 and full.autonomous == 85
    approve = tb.simulate("approve_all", writes, costs=costs)
    assert approve.harmful == 0 and approve.reviews == 85
    # 85 writes with 5 mistakes never earns autonomy at a 1.6% break-even.
    solo = tb.simulate("solo_license", writes, costs=costs)
    assert solo.harmful == 0 and solo.autonomous == 0
    # A fixed 3-in-a-row ladder goes autonomous and lets mistakes through.
    ladder = tb.simulate("fixed_ladder", writes, costs=costs, audit_rate=0.0)
    assert ladder.harmful == 5


def test_guards_hold_flagged_writes_for_review():
    writes = [_write(False, ["confirmation"]), _write(True)]
    out = tb.simulate("guards_only", writes, costs=tb.Costs())
    assert out.harmful == 0 and out.reviews == 1 and out.autonomous == 1


def test_parse_episode_labels_and_guards():
    orders = {"#W1": {"user_id": "u1"}}

    def call(name, args, cid):
        return {"role": "assistant", "tool_calls": [{"id": cid, "function": {"name": name, "arguments": args}}]}

    raw = {
        "task_id": 1, "trial": 0, "reward": 0.0,
        "info": {"task": {"actions": [
            {"name": "cancel_pending_order", "kwargs": {"order_id": "#W1", "reason": "no longer needed"}},
        ]}},
        "traj": [
            call("find_user_id_by_email", {"email": "a@b.c"}, "1"),
            {"role": "tool", "tool_call_id": "1", "name": "find_user_id_by_email", "content": "u1"},
            call("get_order_details", {"order_id": "#W1"}, "2"),
            {"role": "tool", "tool_call_id": "2", "name": "get_order_details", "content": '{"order_id": "#W1"}'},
            {"role": "user", "content": "Yes, please cancel it."},
            call("cancel_pending_order", {"order_id": "#W1", "reason": "no longer needed"}, "3"),
            {"role": "tool", "tool_call_id": "3", "name": "cancel_pending_order", "content": "{}"},
            {"role": "user", "content": "Also change my address."},
            call("modify_user_address", {"user_id": "u1", "address1": "x"}, "4"),
            {"role": "tool", "tool_call_id": "4", "name": "modify_user_address", "content": "{}"},
            call("cancel_pending_order", {"order_id": "#W9", "reason": "x"}, "5"),
            {"role": "tool", "tool_call_id": "5", "name": "cancel_pending_order", "content": "Error: order not found"},
        ],
    }
    episode = tb.parse_episode(raw, orders)
    assert [w.tool for w in episode.writes] == ["cancel_pending_order", "modify_user_address"]
    first, second = episode.writes
    assert first.correct and first.guards == ()
    assert not second.correct and "confirmation" in second.guards


def test_pass_hat_k():
    eps = [tb.Episode(1, t, r) for t, r in enumerate([1, 1, 0, 1])] + [tb.Episode(2, t, 1.0) for t in range(4)]
    assert tb.pass_hat_k(eps, 1) == pytest.approx((0.75 + 1) / 2)
    assert tb.pass_hat_k(eps, 4) == pytest.approx(0.5)
