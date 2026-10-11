"""Evidence-packet builder.

When a detection demotes a task class, a human restores it only after reading
one packet. This assembles that packet from the sources of truth: the run and
its before/after numbers, the detections that fired, the full trace (local
mirror), and the git-backed license history. Recovery is a judgement made on
this evidence - not a blind retry."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

from sololicense.config import Config
from sololicense.db.repositories import detections as detections_repo
from sololicense.db.repositories import events as events_repo
from sololicense.db.repositories import orders as orders_repo
from sololicense.db.repositories import runs as runs_repo
from sololicense.db.repositories import spans as spans_repo


@dataclass(frozen=True)
class EvidencePacket:
    run: dict
    order: dict | None
    detections: list[dict]
    spans: list[dict]
    license_history: list[dict]
    neatlogs_link: str | None
    before_refunded: float
    after_refunded: float
    intended_delta: float = field(default=0.0)

    @property
    def actual_delta(self) -> float:
        return round(self.after_refunded - self.before_refunded, 2)


def _neatlogs_link(config: Config, trace_id: str | None) -> str | None:
    if not trace_id or not config.neatlogs_enabled:
        return None
    return config.neatlogs_trace_url.format(
        app=config.neatlogs_app_url.rstrip("/"),
        project=config.neatlogs_project,
        trace_id=trace_id,
    )


def build_packet(
    conn: sqlite3.Connection, run_id: int, config: Config
) -> EvidencePacket | None:
    """Assemble the evidence packet for one run, or ``None`` if it is unknown."""
    run = runs_repo.get_run(conn, run_id)
    if run is None:
        return None

    trace_id = run["trace_id"]
    detections = detections_repo.list_for_run(conn, run_id)
    order = orders_repo.get_order(conn, run["order_id"])
    history = events_repo.list_events(conn, task_class=run["task_class"], limit=10)
    intended = run["requested_amount"] if run["executed"] else 0.0

    return EvidencePacket(
        run=dict(run),
        order=dict(order) if order else None,
        detections=[dict(d) for d in detections],
        spans=spans_repo.list_for_trace(conn, trace_id) if trace_id else [],
        license_history=[dict(e) for e in history],
        neatlogs_link=_neatlogs_link(config, trace_id),
        before_refunded=run["before_refunded"],
        after_refunded=run["after_refunded"],
        intended_delta=intended,
    )
