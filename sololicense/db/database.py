"""Connection management and schema application.

A thin wrapper over the stdlib ``sqlite3`` module: it hands out connections
configured for safe concurrent use and applies the schema idempotently. All
SQL for the app lives in the repository modules that sit on top of this."""

from __future__ import annotations

import sqlite3
from pathlib import Path

_SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def connect(db_path: Path, *, check_same_thread: bool = True) -> sqlite3.Connection:
    """Open a connection with sensible defaults.

    * ``row_factory`` yields dict-like rows for readable call sites.
    * foreign keys are enforced per-connection (SQLite requires this each time).
    * ``check_same_thread=False`` lets a Streamlit cached resource reuse one
      connection across the framework's worker threads (demo serialises writes).
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(
        db_path,
        detect_types=sqlite3.PARSE_DECLTYPES,
        check_same_thread=check_same_thread,
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def apply_schema(conn: sqlite3.Connection) -> None:
    """Create every table/index if absent. Safe to call on every startup."""
    conn.executescript(_SCHEMA_PATH.read_text(encoding="utf-8"))
    _migrate_runs(conn)
    conn.commit()


_ADDED_COLUMNS = {
    "orders": (
        ("credit_issued", "REAL NOT NULL DEFAULT 0"),
        ("email", "TEXT"),
        ("ordered_at", "TEXT"),                     # ISO date the customer paid
        ("currency", "TEXT NOT NULL DEFAULT 'usd'"),
        ("source", "TEXT NOT NULL DEFAULT 'manual'"),  # manual | sample | csv | stripe
        ("external_id", "TEXT"),                    # e.g. Stripe charge id
        ("customer_ref", "TEXT"),                   # e.g. Stripe customer id
    ),
    "license_state": (
        ("successes", "INTEGER NOT NULL DEFAULT 0"),
        ("failures", "INTEGER NOT NULL DEFAULT 0"),
    ),
    "runs": (
        ("recovered", "INTEGER NOT NULL DEFAULT 0"),   # agent fixed a failed action
        ("ticket_id", "INTEGER"),
    ),
}


def _migrate_runs(conn: sqlite3.Connection) -> None:
    for table, columns in _ADDED_COLUMNS.items():
        existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
        for name, ddl in columns:
            if name not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(runs)")}
    if "idempotency_key" not in columns:
        conn.execute("ALTER TABLE runs ADD COLUMN idempotency_key TEXT")
    if "actor_id" not in columns:
        conn.execute("ALTER TABLE runs ADD COLUMN actor_id TEXT NOT NULL DEFAULT 'system:license-service'")
    if "actor_role" not in columns:
        conn.execute("ALTER TABLE runs ADD COLUMN actor_role TEXT NOT NULL DEFAULT 'admin'")
    if "policy_version" not in columns:
        conn.execute("ALTER TABLE runs ADD COLUMN policy_version INTEGER")
    event_columns = {row["name"] for row in conn.execute("PRAGMA table_info(license_events)")}
    if "actor_id" not in event_columns:
        conn.execute("ALTER TABLE license_events ADD COLUMN actor_id TEXT NOT NULL DEFAULT 'system:license-service'")
    if "actor_role" not in event_columns:
        conn.execute("ALTER TABLE license_events ADD COLUMN actor_role TEXT NOT NULL DEFAULT 'admin'")
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_runs_idempotency_executed
            ON runs (idempotency_key)
            WHERE idempotency_key IS NOT NULL AND executed = 1
        """
    )


def init_db(db_path: Path, *, check_same_thread: bool = True) -> sqlite3.Connection:
    """Open a connection and guarantee the schema exists."""
    conn = connect(db_path, check_same_thread=check_same_thread)
    apply_schema(conn)
    return conn
