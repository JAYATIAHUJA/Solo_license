"""The cfo.ai model for the coding agent: explicit assumptions, consistent numbers."""

from __future__ import annotations

import sqlite3

from planning.cfo import coding_model as m


def test_solo_license_is_the_cheapest_way_to_run_a_coding_agent():
    ask, full, solo = m.scenarios()
    assert solo.total < full.total < ask.total
    assert m.summary()["saving_vs_ask_every_time"] == round(ask.total - solo.total, 2)


def test_unit_economics_and_break_even_are_consistent():
    unit = m.unit_cost_per_dev()
    assert unit["cost_per_dev_month"] < 1.0 and unit["gross_margin_pct"] > 90
    seats = m.break_even_seats()
    assert seats * (m.PRICE_PER_DEV_MONTH - unit["cost_per_dev_month"]) >= m.FIXED_MONTHLY_COSTS


def test_projection_reaches_profit_and_cash_follows_profit():
    rows = m.projection()
    assert rows[-1]["profit"] > 0
    for prev, row in zip(rows, rows[1:]):
        assert abs(prev["cash"] + row["profit"] - row["cash"]) < 0.02


def test_measured_auto_share_from_real_decisions(tmp_path):
    db = tmp_path / "x.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE agent_decisions (decision TEXT)")
    conn.executemany("INSERT INTO agent_decisions VALUES (?)", [("allow",), ("allow",), ("ask",), ("deny",)])
    conn.commit()
    conn.close()
    summary = m.summary(db)
    assert summary["measured"]["auto_share"] == 0.5
    assert summary["cost_per_dev_month_measured_solo"] > summary["cost_per_dev_month"][-1]["total"]
