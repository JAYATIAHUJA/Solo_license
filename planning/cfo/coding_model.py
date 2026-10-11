"""Financial model for Solo License for coding agents (the cfo.ai plan).

The thesis: **a permission prompt is a cost, and so is a mistake.** Today a
developer picks one of two bad deals - approve everything ("ask before
changes") and pay in interruptions, or grant full access and pay in reviews of
over-edited diffs and the occasional destructive action. Solo License lets
each kind of action run alone only once its verified record makes that the
cheaper choice, so a team pays neither bill.

Every number is an explicit assumption below, per developer per month. When a
database with real hook decisions exists, the share of actions the gate
auto-allowed is *measured* instead of assumed.

    python -m planning.cfo.coding_model
"""

from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path

from sololicense.coding.ladder import DEVELOPER_HOURLY_COST, MINUTES_BY_LEVEL

# --- Developer time (assumptions) -----------------------------------------
WORKDAYS_PER_MONTH = 20
PROMPTS_PER_DAY = 40                 # permission prompts in "ask before changes" mode
MINUTES_PER_PROMPT = MINUTES_BY_LEVEL[0]   # stop, read the command, approve, get back in
OVER_EDITED_TURNS_PER_WEEK = 5       # turns whose diff is far bigger than the request
REVIEW_MINUTES_PER_OVER_EDIT = 12    # reading and reverting the extra lines
FULL_ACCESS_INCIDENTS_PER_MONTH = 0.05   # destructive action reaching the repo/remote
INCIDENT_COST = 8 * DEVELOPER_HOURLY_COST  # a day of recovery

# --- What Solo License changes (assumptions, replaced by measurements) -----
AUTO_SHARE_ONCE_EARNED = 0.75        # share of prompts answered by an earned license
OVER_EDITS_CAUGHT = 0.9              # sent back at turn end, before a person reads them
INCIDENTS_PREVENTED = 0.9            # forbidden actions denied, failures demote at once

# --- Pricing and company costs ----------------------------------------------
PRICE_PER_DEV_MONTH = 15.0           # Team plan; the plugin itself is free
JEV_TOKENS_PER_TURN = 3_000          # one diff grade per turn (state + question)
TURNS_PER_DAY = 30
JEV_PRICE_PER_MILLION_INPUT = 0.042  # TypeSafe's published price, output free
HOSTING_PER_DEV_MONTH = 0.40         # shared ledger + dashboard
FIXED_MONTHLY_COSTS = 4_000.0        # infra, tools, domain; founders unpaid
CASH_ON_HAND = 25_000.0
STARTING_SEATS = 50
MONTHLY_SEAT_GROWTH = 0.30


def _usd(minutes: float) -> float:
    return round(minutes / 60.0 * DEVELOPER_HOURLY_COST, 2)


@dataclass(frozen=True)
class Scenario:
    name: str
    approval_minutes: float
    over_edit_minutes: float
    incident_cost: float

    @property
    def total(self) -> float:
        return round(_usd(self.approval_minutes) + _usd(self.over_edit_minutes) + self.incident_cost, 2)


def scenarios(auto_share: float = AUTO_SHARE_ONCE_EARNED) -> list[Scenario]:
    """Monthly cost per developer of each way to run a coding agent."""
    prompts = PROMPTS_PER_DAY * WORKDAYS_PER_MONTH
    over_edit = OVER_EDITED_TURNS_PER_WEEK * 4 * REVIEW_MINUTES_PER_OVER_EDIT
    full_access_risk = FULL_ACCESS_INCIDENTS_PER_MONTH * INCIDENT_COST
    return [
        Scenario("Ask before every change", prompts * MINUTES_PER_PROMPT, over_edit, 0.0),
        Scenario("Full access", 0.0, over_edit, round(full_access_risk, 2)),
        Scenario(
            "Solo License",
            prompts * (1 - auto_share) * MINUTES_PER_PROMPT,
            round(over_edit * (1 - OVER_EDITS_CAUGHT), 2),
            round(full_access_risk * (1 - INCIDENTS_PREVENTED), 2),
        ),
    ]


def unit_cost_per_dev() -> dict:
    jev = TURNS_PER_DAY * WORKDAYS_PER_MONTH * JEV_TOKENS_PER_TURN / 1_000_000 * JEV_PRICE_PER_MILLION_INPUT
    total = jev + HOSTING_PER_DEV_MONTH
    return {
        "jev_per_dev_month": round(jev, 4),
        "hosting_per_dev_month": HOSTING_PER_DEV_MONTH,
        "cost_per_dev_month": round(total, 4),
        "gross_margin_pct": round(100 * (PRICE_PER_DEV_MONTH - total) / PRICE_PER_DEV_MONTH, 1),
    }


def projection(months: int = 12) -> list[dict]:
    """Seats, revenue, costs and cash month by month."""
    unit = unit_cost_per_dev()["cost_per_dev_month"]
    cash, seats, rows = CASH_ON_HAND, float(STARTING_SEATS), []
    for month in range(1, months + 1):
        revenue = seats * PRICE_PER_DEV_MONTH
        costs = FIXED_MONTHLY_COSTS + seats * unit
        cash += revenue - costs
        rows.append({"month": month, "seats": int(seats), "revenue": round(revenue, 2),
                     "costs": round(costs, 2), "profit": round(revenue - costs, 2), "cash": round(cash, 2)})
        seats *= 1 + MONTHLY_SEAT_GROWTH
    return rows


def break_even_seats() -> int:
    unit = unit_cost_per_dev()["cost_per_dev_month"]
    return int(FIXED_MONTHLY_COSTS // (PRICE_PER_DEV_MONTH - unit)) + 1


def measured_auto_share(db_path: Path) -> dict | None:
    """Share of gate decisions an earned license answered, from real hook calls."""
    if not db_path.exists():
        return None
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(decision = 'allow'), 0), COALESCE(SUM(decision = 'deny'), 0) "
            "FROM agent_decisions"
        ).fetchone()
    except sqlite3.OperationalError:
        return None
    finally:
        conn.close()
    total, allowed, denied = (int(v) for v in row)
    if not total:
        return None
    return {"decisions": total, "auto_allowed": allowed, "denied": denied,
            "auto_share": round(allowed / total, 3)}


def summary(db_path: Path | None = None) -> dict:
    measured = measured_auto_share(db_path) if db_path else None
    rows = scenarios()
    solo = rows[-1].total
    data = {
        "assumptions": {
            "developer_hourly_cost": DEVELOPER_HOURLY_COST,
            "prompts_per_day": PROMPTS_PER_DAY,
            "minutes_per_prompt": MINUTES_PER_PROMPT,
            "over_edited_turns_per_week": OVER_EDITED_TURNS_PER_WEEK,
            "review_minutes_per_over_edit": REVIEW_MINUTES_PER_OVER_EDIT,
            "full_access_incidents_per_month": FULL_ACCESS_INCIDENTS_PER_MONTH,
            "incident_cost": INCIDENT_COST,
            "auto_share_once_earned": AUTO_SHARE_ONCE_EARNED,
            "price_per_dev_month": PRICE_PER_DEV_MONTH,
        },
        "cost_per_dev_month": [{**asdict(s), "total": s.total} for s in rows],
        "saving_vs_ask_every_time": round(rows[0].total - solo, 2),
        "saving_vs_full_access": round(rows[1].total - solo, 2),
        "roi_multiple": round((rows[0].total - solo) / PRICE_PER_DEV_MONTH, 1),
        "unit_economics": unit_cost_per_dev(),
        "break_even_seats": break_even_seats(),
        "projection": projection(),
    }
    if measured:
        data["measured"] = measured
        data["cost_per_dev_month_measured_solo"] = scenarios(measured["auto_share"])[-1].total
    return data


def main() -> None:
    import json

    from sololicense.config import load_config

    print(json.dumps(summary(load_config().db_path), indent=2))


if __name__ == "__main__":
    main()
