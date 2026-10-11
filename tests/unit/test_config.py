from pathlib import Path

from dataclasses import replace

from sololicense.config import load_config
from sololicense.domain.models import RunStatus


def test_load_config_reads_ledger_repo(monkeypatch, tmp_path):
    ledger_repo = tmp_path / "ledger-repo"
    monkeypatch.setenv("SOLO_LEDGER_REPO", str(ledger_repo))

    config = load_config()

    assert config.ledger_repo == ledger_repo


def test_approved_status_is_a_run_status_value():
    assert RunStatus.APPROVED.value == "approved"


def test_groq_and_zcode_provider_settings_enable_the_configured_model():
    base = load_config()
    groq = replace(
        base,
        llm_provider="groq",
        groq_api_key="groq-test-key",
        groq_model="groq-test-model",
    )
    zcode = replace(
        base,
        llm_provider="zcode_glm",
        zcode_api_key="zcode-test-key",
        zcode_model="glm-test-model",
    )

    assert groq.llm_enabled is True
    assert groq.llm_api_key == "groq-test-key"
    assert groq.llm_model == "groq-test-model"
    assert zcode.llm_enabled is True
    assert zcode.llm_api_key == "zcode-test-key"
    assert zcode.llm_model == "glm-test-model"


def test_legacy_database_without_new_columns_migrates(tmp_path):
    import sqlite3

    from sololicense.db.database import init_db

    db = tmp_path / "legacy.db"
    legacy = sqlite3.connect(db)
    legacy.executescript(
        """
        CREATE TABLE orders (order_id TEXT PRIMARY KEY, customer TEXT NOT NULL,
            amount REAL NOT NULL, refunded_amount REAL NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'paid', updated_at TEXT);
        CREATE TABLE runs (id INTEGER PRIMARY KEY AUTOINCREMENT, task_class TEXT NOT NULL,
            order_id TEXT NOT NULL, requested_amount REAL NOT NULL, level_at_run INTEGER NOT NULL,
            decision TEXT NOT NULL, status TEXT NOT NULL, executed INTEGER NOT NULL DEFAULT 0,
            before_refunded REAL NOT NULL, after_refunded REAL NOT NULL,
            fault_mode TEXT NOT NULL DEFAULT 'none', trace_id TEXT, notes TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')));
        """
    )
    legacy.close()

    conn = init_db(db)

    run_columns = {r["name"] for r in conn.execute("PRAGMA table_info(runs)")}
    order_columns = {r["name"] for r in conn.execute("PRAGMA table_info(orders)")}
    assert {"idempotency_key", "actor_id"} <= run_columns
    assert "credit_issued" in order_columns
