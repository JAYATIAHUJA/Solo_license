from __future__ import annotations

import pytest

from sololicense.db.database import apply_schema
from sololicense.domain.policy import PolicyRule, evaluate_runs


def test_policy_rule_rejects_invalid_sample_and_pass_rate():
    """A policy with impossible evaluation terms must never be activated."""
    with pytest.raises(ValueError, match="evaluation window"):
        PolicyRule("refund", "refund", 2, 50, 0, 3, 1.0)
    with pytest.raises(ValueError, match="pass rate"):
        PolicyRule("refund", "refund", 2, 50, 3, 3, 1.1)


def test_evaluation_needs_minimum_samples_and_pass_rate():
    """Promotion requires enough recent verified evidence at the stated rate."""
    rule = PolicyRule("refund", "refund", 2, 50, 5, 3, 0.8)

    assert evaluate_runs([True, True], rule).eligible is False
    assert evaluate_runs([True, True, False], rule).eligible is False
    assert evaluate_runs([True, True, True], rule).eligible is True


def test_schema_migrates_an_existing_runs_table_to_policy_audit_fields(tmp_path):
    """An installed workspace gains policy records without being rebuilt."""
    import sqlite3

    conn = sqlite3.connect(tmp_path / "legacy.db")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_class TEXT NOT NULL,
            order_id TEXT NOT NULL,
            requested_amount REAL NOT NULL,
            level_at_run INTEGER NOT NULL,
            decision TEXT NOT NULL,
            status TEXT NOT NULL,
            executed INTEGER NOT NULL DEFAULT 0,
            before_refunded REAL NOT NULL,
            after_refunded REAL NOT NULL,
            fault_mode TEXT NOT NULL DEFAULT 'none',
            trace_id TEXT,
            notes TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )

    apply_schema(conn)

    columns = {row[1] for row in conn.execute("PRAGMA table_info(runs)")}
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert "policy_version" in columns
    assert {"policies", "policy_rules", "policy_impacts", "execution_permits"} <= tables


def test_existing_demo_database_boots_with_a_v1_policy(tmp_path):
    """A real startup migrates a pre-policy workspace without losing the worker."""
    import sqlite3
    import subprocess
    from dataclasses import replace

    from sololicense.bootstrap import build_app
    from sololicense.config import load_config
    from sololicense.db.seed import seed
    from sololicense.domain.models import RefundRequest, RunStatus

    db_path = tmp_path / "legacy.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_class TEXT NOT NULL, order_id TEXT NOT NULL, requested_amount REAL NOT NULL,
            level_at_run INTEGER NOT NULL, decision TEXT NOT NULL, status TEXT NOT NULL,
            executed INTEGER NOT NULL DEFAULT 0, before_refunded REAL NOT NULL,
            after_refunded REAL NOT NULL, fault_mode TEXT NOT NULL DEFAULT 'none',
            trace_id TEXT, notes TEXT, created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    conn.commit()
    conn.close()

    ledger_repo = tmp_path / "ledger"
    ledger_repo.mkdir()
    for args in (("init", "-q"), ("config", "user.name", "Policy test"), ("config", "user.email", "policy@example.com")):
        subprocess.run(["git", *args], cwd=ledger_repo, check=True)
    config = replace(
        load_config(), db_path=db_path, ledger_repo=ledger_repo,
        llm_provider="deterministic", neatlogs_api_key="", demo_mode=False,
    )
    context = build_app(config)
    try:
        assert context.policy_service.active().version == 1
        seed(context.conn, context.config)
        result = context.worker.run_refund(RefundRequest("ORD-1001", "Ada", 10.0, "late"))
        assert result.status is RunStatus.CLEAN
    finally:
        context.conn.close()


def test_first_policy_binds_legacy_runs_to_the_migrated_v1(tmp_path):
    """Historical evidence belongs to the policy that reproduces old defaults."""
    from dataclasses import replace

    from sololicense.config import load_config
    from sololicense.db.database import init_db
    from sololicense.services.policy_service import PolicyService

    config = replace(load_config(), db_path=tmp_path / "workspace.db", neatlogs_api_key="")
    conn = init_db(config.db_path)
    conn.execute(
        "INSERT INTO orders (order_id, customer, amount) VALUES ('legacy-order', 'Legacy customer', 10)"
    )
    conn.execute(
        """
        INSERT INTO runs
            (task_class, order_id, requested_amount, level_at_run, decision, status,
             executed, before_refunded, after_refunded, fault_mode)
        VALUES ('refund', 'legacy-order', 10, 2, 'AUTO_EXECUTE', 'clean', 1, 0, 10, 'none')
        """
    )
    conn.commit()

    policy = PolicyService(conn, config).ensure_default_policy()
    row = conn.execute("SELECT policy_version FROM runs WHERE order_id = 'legacy-order'").fetchone()

    assert row["policy_version"] == policy.version
