"""Coding events move out of the payments ledger once, and only once."""

from __future__ import annotations

from sololicense.db.database import apply_schema, init_db


def test_old_coding_events_are_copied_once_and_refund_events_stay(tmp_path):
    conn = init_db(tmp_path / "old.db")
    conn.execute(
        "INSERT INTO license_events (task_class, kind, from_level, to_level, reason, actor_id, git_sha) "
        "VALUES ('test-run@shop-api', 'promote', 0, 1, '3 verified', 'system:coding-gate', 'abc1234')")
    conn.execute(
        "INSERT INTO license_events (task_class, kind, from_level, to_level, reason) "
        "VALUES ('refund', 'promote', 0, 1, 'x')")
    conn.commit()

    apply_schema(conn)
    apply_schema(conn)

    rows = [tuple(r) for r in conn.execute(
        "SELECT repo, principal, action_class, kind, from_level, to_level, actor_id, git_sha FROM agent_events")]
    assert rows == [("shop-api", "main", "test-run", "promote", 0, 1, "system:coding-gate", "abc1234")]
