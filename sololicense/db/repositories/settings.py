"""Settings repository — operator-editable key/value configuration."""

from __future__ import annotations

import sqlite3


def get_all(conn: sqlite3.Connection) -> dict[str, str]:
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    return {row["key"]: row["value"] for row in rows}


def set_many(conn: sqlite3.Connection, values: dict[str, str]) -> None:
    """Upsert several settings. The caller commits."""
    conn.executemany(
        """
        INSERT INTO settings (key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value,
                                       updated_at = datetime('now')
        """,
        list(values.items()),
    )
