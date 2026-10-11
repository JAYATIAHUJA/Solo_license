-- Solo License schema. One file, applied idempotently at startup.
-- Pragmas: enforce referential integrity and durable, concurrent reads.
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

-- The "real world" the agent acts on. orders.refunded_amount is the ONLY
-- authority on whether a refund actually landed — the verifier reads it
-- back after every execution rather than trusting the tool's response.
CREATE TABLE IF NOT EXISTS orders (
    order_id         TEXT PRIMARY KEY,
    customer         TEXT NOT NULL,
    amount           REAL NOT NULL,            -- original order total
    refunded_amount  REAL NOT NULL DEFAULT 0,  -- verified side effect (refund)
    credit_issued    REAL NOT NULL DEFAULT 0,  -- verified side effect (store_credit)
    status           TEXT NOT NULL DEFAULT 'paid',
    updated_at       TEXT NOT NULL DEFAULT (datetime('now'))
    -- email, ordered_at, currency, source, external_id, customer_ref are
    -- added by database._migrate so older databases gain them too.
);

-- The autonomy dial. One row per task class; the live source of truth the
-- UI renders and the agent consults before acting.
CREATE TABLE IF NOT EXISTS license_state (
    task_class             TEXT PRIMARY KEY,
    level                  INTEGER NOT NULL DEFAULT 0,  -- LicenseLevel
    consecutive_clean_runs INTEGER NOT NULL DEFAULT 0,
    quarantined            INTEGER NOT NULL DEFAULT 0,  -- 0/1
    demoted_from           INTEGER,                     -- level it fell from
    successes              INTEGER NOT NULL DEFAULT 0,  -- verified evidence
    failures               INTEGER NOT NULL DEFAULT 0,
    updated_at             TEXT NOT NULL DEFAULT (datetime('now'))
);

-- One row per refund run. Carries the before/after numbers that make a
-- neatlogs trace comparison concrete, plus the trace id for deep-linking.
CREATE TABLE IF NOT EXISTS runs (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    task_class       TEXT NOT NULL,
    order_id         TEXT NOT NULL,
    requested_amount REAL NOT NULL,
    level_at_run     INTEGER NOT NULL,         -- effective level when decided
    decision         TEXT NOT NULL,            -- Decision name
    status           TEXT NOT NULL,            -- RunStatus value
    executed         INTEGER NOT NULL DEFAULT 0,
    before_refunded  REAL NOT NULL,            -- orders.refunded_amount before
    after_refunded   REAL NOT NULL,            -- orders.refunded_amount after
    idempotency_key  TEXT,
    actor_id         TEXT NOT NULL DEFAULT 'system:license-service',
    actor_role       TEXT NOT NULL DEFAULT 'admin',
    fault_mode       TEXT NOT NULL DEFAULT 'none',
    trace_id         TEXT,
    notes            TEXT,
    created_at       TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (order_id) REFERENCES orders (order_id)
);
CREATE INDEX IF NOT EXISTS idx_runs_created ON runs (created_at DESC);
-- idx_runs_idempotency_executed is created in database._migrate_runs, after
-- older databases have gained the idempotency_key column.

-- Detections surfaced as incidents. Each row is one rule firing on one run.
CREATE TABLE IF NOT EXISTS detections (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      INTEGER NOT NULL,
    rule        TEXT NOT NULL,                 -- e.g. state_mismatch
    severity    TEXT NOT NULL,                 -- info | warning | critical
    message     TEXT NOT NULL,
    trace_id    TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (run_id) REFERENCES runs (id)
);
CREATE INDEX IF NOT EXISTS idx_detections_run ON detections (run_id);

-- The git-backed license ledger. Every promote / demote / restore is a row
-- here AND a git commit; git_sha links the two so Entire can graph/explain
-- the history of autonomy changes.
CREATE TABLE IF NOT EXISTS license_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    task_class  TEXT NOT NULL,
    kind        TEXT NOT NULL,                 -- promote | demote | restore
    from_level  INTEGER NOT NULL,
    to_level    INTEGER NOT NULL,
    reason      TEXT NOT NULL,
    run_id      INTEGER,
    actor_id    TEXT NOT NULL DEFAULT 'system:license-service',
    actor_role  TEXT NOT NULL DEFAULT 'admin',
    git_sha     TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (run_id) REFERENCES runs (id)
);
CREATE INDEX IF NOT EXISTS idx_license_events_class ON license_events (task_class, created_at DESC);

-- Local mirror of observability spans, written for every run so the evidence
-- packet and before/after comparison work even with no neatlogs key present.
CREATE TABLE IF NOT EXISTS spans (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    trace_id    TEXT NOT NULL,
    run_id      INTEGER,
    name        TEXT NOT NULL,
    attributes  TEXT NOT NULL DEFAULT '{}',    -- JSON
    status      TEXT NOT NULL DEFAULT 'ok',
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_spans_trace ON spans (trace_id);

-- Armed fault for the next run of a task class. The UI sets a row here; the
-- worker consumes and clears it, so a fault deterministically affects exactly
-- one run. Default 'none' means run normally.
CREATE TABLE IF NOT EXISTS armed_faults (
    task_class  TEXT PRIMARY KEY,
    mode        TEXT NOT NULL DEFAULT 'none',
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Operator-editable settings (onboarding + the Settings screen). Values here
-- override environment defaults at startup; secrets are never echoed to the UI.
CREATE TABLE IF NOT EXISTS settings (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Free-text customer requests handled by the intake agent.
CREATE TABLE IF NOT EXISTS intakes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    message     TEXT NOT NULL,
    order_id    TEXT,
    amount      REAL,
    reason      TEXT,
    source      TEXT NOT NULL DEFAULT 'deterministic',
    run_id      INTEGER,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Customer messages waiting for (or handled by) the agent. They arrive by
-- paste, by the inbox webhook (helpdesk / email forwarder) or by CSV import.
CREATE TABLE IF NOT EXISTS tickets (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    source      TEXT NOT NULL DEFAULT 'paste',   -- paste | webhook | sample
    sender      TEXT,                            -- customer email, if known
    subject     TEXT,
    body        TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'new',     -- new | done | waiting | needs_human
    outcome     TEXT,                            -- one-line result for the inbox
    reply       TEXT,                            -- reply drafted for the customer
    steps       TEXT NOT NULL DEFAULT '[]',      -- JSON: the agent's steps
    run_id      INTEGER,
    trace_id    TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    handled_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_tickets_created ON tickets (created_at DESC);
