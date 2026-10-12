from sololicense.config import load_config, with_overrides


def test_load_config_reads_ledger_repo(monkeypatch, tmp_path):
    ledger_repo = tmp_path / "ledger-repo"
    monkeypatch.setenv("SOLO_LEDGER_REPO", str(ledger_repo))

    config = load_config()

    assert config.ledger_repo == ledger_repo


def test_saved_settings_override_the_environment():
    config = with_overrides(load_config(), {
        "neatlogs_project": " team-a ", "typesafe_api_key": "ts-key",
        "trust_confidence": "2", "jev_endpoint": "",
    })

    assert config.neatlogs_project == "team-a"
    assert config.typesafe_api_key == "ts-key"
    assert config.trust_confidence == 0.999
    assert config.jev_endpoint == load_config().jev_endpoint


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
    agent_tables = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE name LIKE 'agent_%'")}
    assert {"idempotency_key", "actor_id"} <= run_columns
    assert "credit_issued" in order_columns
    assert {"agent_events", "agent_licenses", "agent_decisions"} <= agent_tables
