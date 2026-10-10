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
    conn.commit()


def init_db(db_path: Path, *, check_same_thread: bool = True) -> sqlite3.Connection:
    """Open a connection and guarantee the schema exists."""
    conn = connect(db_path, check_same_thread=check_same_thread)
    apply_schema(conn)
    return conn
