"""License-state repository - reads/writes the autonomy dial and maps rows to
and from the pure :class:`~sololicense.domain.license.LicenseState`."""

from __future__ import annotations

import sqlite3

from sololicense.domain.license import LicenseLevel, LicenseState


def _row_to_state(row: sqlite3.Row) -> LicenseState:
    return LicenseState(
        task_class=row["task_class"],
        level=LicenseLevel(row["level"]),
        consecutive_clean_runs=row["consecutive_clean_runs"],
        quarantined=bool(row["quarantined"]),
        demoted_from=(
            LicenseLevel(row["demoted_from"])
            if row["demoted_from"] is not None
            else None
        ),
        successes=row["successes"],
        failures=row["failures"],
    )


def get_state(conn: sqlite3.Connection, task_class: str) -> LicenseState | None:
    row = conn.execute(
        "SELECT * FROM license_state WHERE task_class = ?", (task_class,)
    ).fetchone()
    return _row_to_state(row) if row else None


def list_states(conn: sqlite3.Connection) -> list[LicenseState]:
    rows = conn.execute(
        "SELECT * FROM license_state ORDER BY task_class"
    ).fetchall()
    return [_row_to_state(r) for r in rows]


def upsert_state(conn: sqlite3.Connection, state: LicenseState) -> None:
    """Insert or replace the dial for a task class. The caller commits."""
    conn.execute(
        """
        INSERT INTO license_state
            (task_class, level, consecutive_clean_runs, quarantined,
             demoted_from, successes, failures, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
        ON CONFLICT(task_class) DO UPDATE SET
            level = excluded.level,
            consecutive_clean_runs = excluded.consecutive_clean_runs,
            quarantined = excluded.quarantined,
            demoted_from = excluded.demoted_from,
            successes = excluded.successes,
            failures = excluded.failures,
            updated_at = excluded.updated_at
        """,
        (
            state.task_class,
            int(state.level),
            state.consecutive_clean_runs,
            1 if state.quarantined else 0,
            int(state.demoted_from) if state.demoted_from is not None else None,
            state.successes,
            state.failures,
        ),
    )
