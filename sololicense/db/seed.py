"""Seed the database to a known, demo-ready state.

Running this resets all *dynamic* tables (runs, detections, events, spans,
armed faults) and reinstalls a fixed set of orders plus a starting dial of
``refund = L2``. From there the demo climbs to L3 on clean runs and crashes to
L0 on an injected fault. Idempotent: run it as often as you like."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from sololicense.config import Config, load_config
from sololicense.db.database import init_db
from sololicense.db.repositories import license as license_repo
from sololicense.domain.license import LicenseLevel, LicenseState
from sololicense.domain.task_classes import TASK_CLASSES


@dataclass(frozen=True)
class SeedOrder:
    order_id: str
    customer: str
    amount: float


# A spread of amounts: most sit under the default $50 L2 ceiling (clean
# auto-execute path); ORD-1004 sits above it (draft / policy-violation demo).
SEED_ORDERS: tuple[SeedOrder, ...] = (
    SeedOrder("ORD-1001", "Ada Lovelace", 25.00),
    SeedOrder("ORD-1002", "Grace Hopper", 40.00),
    SeedOrder("ORD-1003", "Alan Turing", 15.00),
    SeedOrder("ORD-1004", "Katherine Johnson", 120.00),
    SeedOrder("ORD-1005", "Linus Torvalds", 45.00),
)

_DYNAMIC_TABLES = ("detections", "spans", "license_events", "runs", "armed_faults", "intakes")

# Demo starting rungs: refunds have already earned L2; store credit is newer
# and starts at L1, so the two ladders visibly move independently.
DEMO_LEVELS = {"refund": LicenseLevel.L2, "store_credit": LicenseLevel.L1}


def seed(conn: sqlite3.Connection, config: Config) -> None:
    """Reset dynamic state and install the fixed demo fixtures."""
    for table in _DYNAMIC_TABLES:
        conn.execute(f"DELETE FROM {table}")
    conn.execute("DELETE FROM orders")

    conn.executemany(
        "INSERT INTO orders (order_id, customer, amount, refunded_amount, status)"
        " VALUES (?, ?, ?, 0, 'paid')",
        [(o.order_id, o.customer, o.amount) for o in SEED_ORDERS],
    )

    for key in TASK_CLASSES:
        level = DEMO_LEVELS.get(key, LicenseLevel.L0)
        license_repo.upsert_state(conn, LicenseState(task_class=key, level=level))
    conn.commit()


def main() -> None:
    config = load_config()
    config.db_path.unlink(missing_ok=True)
    conn = init_db(config.db_path)
    seed(conn, config)
    conn.close()
    print(
        f"Seeded {len(SEED_ORDERS)} orders; dials "
        + ", ".join(f"{k}={DEMO_LEVELS.get(k, LicenseLevel.L0).name}" for k in TASK_CLASSES)
        + f" in {config.db_path}."
    )


if __name__ == "__main__":
    main()
