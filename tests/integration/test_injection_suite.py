"""30 hostile messages: none may move money, and each is stopped by the layer
it is aimed at (see :mod:`sololicense.bench.injection`)."""

from __future__ import annotations

import pytest

from sololicense.bench.injection import ATTACKS, run_suite, summarize


@pytest.fixture(scope="module")
def results():
    return run_suite()


def test_suite_has_thirty_attacks_across_every_layer():
    assert len(ATTACKS) == 30
    assert {a.expected for a in ATTACKS} == {"intake", "order_lookup", "policy", "licence", "permit"}


def test_no_attack_changes_any_order(results):
    moved = [(r.attack.message, r.money_moved) for r in results if r.money_moved != 0]
    assert moved == []


def test_each_attack_is_stopped_by_the_layer_it_targets(results):
    wrong = [(r.attack.message, r.attack.expected, r.stopped_at) for r in results
             if r.stopped_at != r.attack.expected]
    assert wrong == []
    assert summarize(results)["not_stopped"] == 0


def test_a_fooled_model_is_still_refused_a_write_permit(results):
    fooled = [r for r in results if r.attack.model_fooled]
    assert fooled and all(r.stopped_at == "permit" for r in fooled)
