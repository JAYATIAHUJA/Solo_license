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
    _migrate_v3(conn)
    _migrate_principals(conn)
    _migrate_sessions(conn)
    conn.commit()


def _migrate_v3(conn: sqlite3.Connection) -> None:
    """Coding events used to share ``license_events`` with the payments agent
    (as ``<class>@<repo>``). Copy them into ``agent_events`` the first time."""
    if conn.execute("SELECT 1 FROM agent_events LIMIT 1").fetchone():
        return
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'license_events'").fetchone():
        return
    conn.execute(
        """
        INSERT INTO agent_events (repo, action_class, kind, from_level, to_level, reason, actor_id, git_sha, created_at)
        SELECT substr(task_class, instr(task_class, '@') + 1), substr(task_class, 1, instr(task_class, '@') - 1),
               kind, from_level, to_level, reason, actor_id, git_sha, created_at
          FROM license_events WHERE task_class LIKE '%@%' ORDER BY id
        """
    )


def _migrate_principals(conn: sqlite3.Connection) -> None:
    """Add principal identity to coding state without losing old licenses.

    ``agent_licenses`` used ``(repo, action_class)`` as its primary key, so
    SQLite cannot add the new key with ``ALTER TABLE``. Rebuild that one table
    when opening a pre-v3 database; the other tables only need nullable-free
    defaulted columns.
    """
    license_columns = {row["name"] for row in conn.execute("PRAGMA table_info(agent_licenses)")}
    if "principal" not in license_columns:
        conn.execute("ALTER TABLE agent_licenses RENAME TO agent_licenses_legacy")
        conn.execute(
            """
            CREATE TABLE agent_licenses (
                repo TEXT NOT NULL,
                principal TEXT NOT NULL DEFAULT 'main',
                action_class TEXT NOT NULL,
                level INTEGER NOT NULL DEFAULT 0,
                successes INTEGER NOT NULL DEFAULT 0,
                failures INTEGER NOT NULL DEFAULT 0,
                successes_at_level INTEGER NOT NULL DEFAULT 0,
                demoted_from INTEGER,
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                PRIMARY KEY (repo, principal, action_class)
            )
            """
        )
        conn.execute(
            """
            INSERT INTO agent_licenses
                (repo, principal, action_class, level, successes, failures,
                 successes_at_level, demoted_from, updated_at)
            SELECT repo, 'main', action_class, level, successes, failures,
                   successes_at_level, demoted_from, updated_at
              FROM agent_licenses_legacy
            """
        )
        conn.execute("DROP TABLE agent_licenses_legacy")

    for table in ("agent_decisions", "agent_turns"):
        columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
        if "principal" not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN principal TEXT NOT NULL DEFAULT 'main'")


def _migrate_sessions(conn: sqlite3.Connection) -> None:
    """Upgrade an early digest table keyed only by session_id."""
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='agent_sessions'").fetchone():
        return
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(agent_sessions)")}
    pk = [row["name"] for row in conn.execute("PRAGMA table_info(agent_sessions)") if row["pk"]]
    if "principal" in columns and pk == ["session_id"]:
        conn.execute("ALTER TABLE agent_sessions RENAME TO agent_sessions_legacy")
        conn.execute(
            """CREATE TABLE agent_sessions (
                session_id TEXT NOT NULL, agent TEXT NOT NULL DEFAULT 'claude-code',
                repo TEXT NOT NULL, principal TEXT NOT NULL DEFAULT 'main',
                started_at TEXT NOT NULL DEFAULT (datetime('now')), cost_usd REAL NOT NULL DEFAULT 0,
                model TEXT, digest TEXT NOT NULL DEFAULT '{}', PRIMARY KEY (session_id, principal)
            )"""
        )
        conn.execute(
            """INSERT INTO agent_sessions(session_id, agent, repo, principal, started_at, cost_usd, model, digest)
               SELECT session_id, agent, repo, principal, started_at, cost_usd, model, digest
                 FROM agent_sessions_legacy"""
        )
        conn.execute("DROP TABLE agent_sessions_legacy")


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
    "tickets": (
        ("follows_ticket_id", "INTEGER"),          # the earlier message this one answers
    ),
    "agent_turns": (
        ("entire_checkpoint", "TEXT"),             # last Entire checkpoint before a failure
        ("agent", "TEXT NOT NULL DEFAULT 'claude-code'"),  # which coding agent
        ("principal", "TEXT NOT NULL DEFAULT 'main'"),
    ),
    "agent_decisions": (
        ("agent", "TEXT NOT NULL DEFAULT 'claude-code'"),
        ("principal", "TEXT NOT NULL DEFAULT 'main'"),
    ),
    "agent_repos": (
        ("last_tests", "TEXT"),                    # passed | failed at the last turn check
    ),
    "agent_events": (
        ("trace_id", "TEXT"),                      # the neatlogs trace that recorded the change
        ("entire_checkpoint", "TEXT"),             # the agent's last Entire checkpoint
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
