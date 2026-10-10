"""Live unit economics of autonomy — the cfo.ai margin story, computed from
the runs actually in the database rather than from a static spreadsheet.

The thesis: **the license level is a margin driver.** Each rung trades human
supervision cost for autonomy; incidents trade it back. Assumptions (wage,
volume, minutes per review, incident cost) are operator settings with the
same defaults as :mod:`cfo.model`; the incident rate is *measured* from the
detections this workspace has recorded.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from cfo import model as cfo

SETTING_DEFAULTS: dict[str, float] = {
    "econ_hourly_cost": cfo.LOADED_HUMAN_COST_PER_HOUR,
    "econ_monthly_volume": float(cfo.REFUNDS_PER_MONTH),
    "econ_incident_cost": cfo.INCIDENT_COST,
}


@dataclass(frozen=True)
class Assumptions:
    hourly_cost: float
    monthly_volume: float
    incident_cost: float

    @classmethod
    def from_settings(cls, stored: dict[str, str]) -> "Assumptions":
        def value(key: str) -> float:
            try:
                return max(0.0, float(stored.get(key, "") or SETTING_DEFAULTS[key]))
            except ValueError:
                return SETTING_DEFAULTS[key]

        return cls(
            hourly_cost=value("econ_hourly_cost"),
            monthly_volume=value("econ_monthly_volume"),
            incident_cost=value("econ_incident_cost"),
        )


def cost_per_action(level: int, a: Assumptions) -> float:
    minutes = cfo.SUPERVISION_MINUTES_PER_RUN[level]
    return minutes / 60.0 * a.hourly_cost


def _measured(conn: sqlite3.Connection, task_class: str) -> dict:
    row = conn.execute(
        """
        SELECT COUNT(*) AS runs,
               COALESCE(SUM(executed), 0) AS executed,
               COALESCE(SUM(status = 'clean'), 0) AS clean,
               COALESCE(SUM(status = 'demoted'), 0) AS incidents
          FROM runs WHERE task_class = ?
        """,
        (task_class,),
    ).fetchone()
    executed = int(row["executed"]) + int(row["incidents"])
    return {
        "runs": int(row["runs"]),
        "clean": int(row["clean"]),
        "incidents": int(row["incidents"]),
        # Every demoted run was caught by a detection *before* it was trusted;
        # the rate is what would have leaked without verification.
        "incident_rate": (int(row["incidents"]) / executed) if executed else 0.0,
    }


def class_economics(
    conn: sqlite3.Connection, task_class: str, effective_level: int, a: Assumptions
) -> dict:
    measured = _measured(conn, task_class)
    volume = a.monthly_volume
    baseline = cost_per_action(0, a) * volume
    current = cost_per_action(effective_level, a) * volume
    # Detections catch an incident before the dial trusts the run again, so
    # the residual risk is the measured rate on the share of runs that execute
    # without a human in the loop (L2/L3).
    unattended = volume if effective_level >= 2 else 0.0
    risk = measured["incident_rate"] * unattended * a.incident_cost
    # What the same incident rate would cost if nobody verified side effects.
    blind_risk = measured["incident_rate"] * volume * a.incident_cost
    return {
        "task_class": task_class,
        "level": effective_level,
        **measured,
        "supervision_cost_month": round(current, 2),
        "supervision_cost_l0_month": round(baseline, 2),
        "supervision_saved_month": round(baseline - current, 2),
        "risk_cost_month": round(risk, 2),
        "blind_autonomy_risk_month": round(blind_risk, 2),
        "net_saved_month": round(baseline - current - risk, 2),
        "cost_per_action": round(cost_per_action(effective_level, a), 4),
    }


def workspace_economics(
    conn: sqlite3.Connection, levels: dict[str, int], stored_settings: dict[str, str]
) -> dict:
    a = Assumptions.from_settings(stored_settings)
    classes = [class_economics(conn, key, level, a) for key, level in levels.items()]
    return {
        "assumptions": {
            "hourly_cost": a.hourly_cost,
            "monthly_volume_per_class": a.monthly_volume,
            "incident_cost": a.incident_cost,
            "minutes_per_action_by_level": cfo.SUPERVISION_MINUTES_PER_RUN,
        },
        "classes": classes,
        "supervision_saved_month": round(sum(c["supervision_saved_month"] for c in classes), 2),
        "risk_cost_month": round(sum(c["risk_cost_month"] for c in classes), 2),
        "net_saved_month": round(sum(c["net_saved_month"] for c in classes), 2),
    }
