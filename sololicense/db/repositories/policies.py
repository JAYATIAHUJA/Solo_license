"""SQLite persistence for immutable autonomy policy versions."""

from __future__ import annotations

import sqlite3
from typing import Iterable

from sololicense.domain.policy import PolicyImpact, PolicyRule, PolicyVersion


def _rule(row: sqlite3.Row) -> PolicyRule:
    return PolicyRule(
        task_class=row["task_class"],
        allowed_tool=row["allowed_tool"],
        requires_approval_at_or_above=row["requires_approval_at_or_above"],
        l2_ceiling=row["l2_ceiling"],
        evaluation_window=row["evaluation_window"],
        minimum_samples=row["minimum_samples"],
        minimum_verified_pass_rate=row["minimum_verified_pass_rate"],
    )


def _policy(conn: sqlite3.Connection, row: sqlite3.Row | None) -> PolicyVersion | None:
    if row is None:
        return None
    rules = tuple(
        _rule(item)
        for item in conn.execute(
            "SELECT * FROM policy_rules WHERE policy_id = ? ORDER BY task_class", (row["id"],)
        )
    )
    return PolicyVersion(
        id=row["id"], version=row["version"], name=row["name"], status=row["status"],
        summary=row["summary"], created_by=row["created_by"], created_at=row["created_at"],
        rules=rules,
    )


def active_policy(conn: sqlite3.Connection) -> PolicyVersion | None:
    row = conn.execute("SELECT * FROM policies WHERE status = 'active'").fetchone()
    return _policy(conn, row)


def get_policy(conn: sqlite3.Connection, version: int) -> PolicyVersion | None:
    row = conn.execute("SELECT * FROM policies WHERE version = ?", (version,)).fetchone()
    return _policy(conn, row)


def list_versions(conn: sqlite3.Connection) -> list[PolicyVersion]:
    rows = conn.execute("SELECT * FROM policies ORDER BY version DESC").fetchall()
    return [policy for row in rows if (policy := _policy(conn, row)) is not None]


def create_version(
    conn: sqlite3.Connection, *, name: str, summary: str, rules: Iterable[PolicyRule],
    created_by: str, status: str = "active",
) -> PolicyVersion:
    """Insert one complete version. The caller owns the encompassing transaction."""
    next_version = int(conn.execute("SELECT COALESCE(MAX(version), 0) + 1 FROM policies").fetchone()[0])
    cur = conn.execute(
        "INSERT INTO policies (version, name, status, summary, created_by) VALUES (?, ?, ?, ?, ?)",
        (next_version, name, status, summary, created_by),
    )
    policy_id = int(cur.lastrowid)
    conn.executemany(
        """
        INSERT INTO policy_rules
            (policy_id, task_class, allowed_tool, requires_approval_at_or_above,
             l2_ceiling, evaluation_window, minimum_samples, minimum_verified_pass_rate)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (policy_id, rule.task_class, rule.allowed_tool, rule.requires_approval_at_or_above,
             rule.l2_ceiling, rule.evaluation_window, rule.minimum_samples,
             rule.minimum_verified_pass_rate)
            for rule in rules
        ],
    )
    return get_policy(conn, next_version)  # type: ignore[return-value]


def supersede_active(conn: sqlite3.Connection) -> None:
    conn.execute("UPDATE policies SET status = 'superseded' WHERE status = 'active'")


def insert_impacts(conn: sqlite3.Connection, impacts: Iterable[PolicyImpact]) -> None:
    conn.executemany(
        """
        INSERT INTO policy_impacts
            (previous_version, next_version, task_class, available_samples,
             required_samples, pass_rate, required_pass_rate, action, reason)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (impact.previous_version, impact.next_version, impact.task_class,
             impact.evaluation.sample_size, impact.evaluation.required_samples,
             impact.evaluation.pass_rate, impact.evaluation.required_pass_rate,
             impact.action, impact.reason)
            for impact in impacts
        ],
    )
