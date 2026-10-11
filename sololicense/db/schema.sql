-- Solo License schema. One file, applied idempotently at startup.
-- Pragmas: enforce referential integrity and durable, concurrent reads.
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

-- The "real world" the agent acts on. orders.refunded_amount is the ONLY
-- authority on whether a refund actually landed - the verifier reads it
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
    policy_version   INTEGER,
    fault_mode       TEXT NOT NULL DEFAULT 'none',
    trace_id         TEXT,
    notes            TEXT,
    created_at       TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (order_id) REFERENCES orders (order_id)
);
CREATE INDEX IF NOT EXISTS idx_runs_created ON runs (created_at DESC);
-- idx_runs_idempotency_executed is created in database._migrate_runs, after
-- older databases have gained the idempotency_key column.

-- Immutable workspace policy versions. Only one version is active at a time;
-- runs retain the version that governed their authorization and evaluation.
CREATE TABLE IF NOT EXISTS policies (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    version     INTEGER NOT NULL UNIQUE,
    name        TEXT NOT NULL,
    status      TEXT NOT NULL CHECK (status IN ('active', 'superseded')),
    summary     TEXT NOT NULL DEFAULT '',
    created_by  TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_policies_one_active
    ON policies (status) WHERE status = 'active';

CREATE TABLE IF NOT EXISTS policy_rules (
    id                              INTEGER PRIMARY KEY AUTOINCREMENT,
    policy_id                       INTEGER NOT NULL,
    task_class                      TEXT NOT NULL,
    allowed_tool                    TEXT NOT NULL,
    requires_approval_at_or_above   INTEGER NOT NULL,
    l2_ceiling                      REAL NOT NULL,
    evaluation_window               INTEGER NOT NULL,
    minimum_samples                 INTEGER NOT NULL,
    minimum_verified_pass_rate      REAL NOT NULL,
    FOREIGN KEY (policy_id) REFERENCES policies (id) ON DELETE CASCADE,
    UNIQUE (policy_id, task_class)
);
CREATE INDEX IF NOT EXISTS idx_policy_rules_policy ON policy_rules (policy_id, task_class);

-- Policies are append-only audit records. The only legal transition is active
-- -> superseded during creation of a newer version; rules are never edited.
CREATE TRIGGER IF NOT EXISTS policies_immutable_fields
BEFORE UPDATE OF version, name, summary, created_by, created_at ON policies
BEGIN
    SELECT RAISE(ABORT, 'policy versions are immutable');
END;
CREATE TRIGGER IF NOT EXISTS policies_status_transition
BEFORE UPDATE OF status ON policies
WHEN OLD.status != 'active' OR NEW.status != 'superseded'
BEGIN
    SELECT RAISE(ABORT, 'policy status transition is immutable');
END;
CREATE TRIGGER IF NOT EXISTS policies_immutable_delete
BEFORE DELETE ON policies
BEGIN
    SELECT RAISE(ABORT, 'policy versions are immutable');
END;
CREATE TRIGGER IF NOT EXISTS policy_rules_immutable_update
BEFORE UPDATE ON policy_rules
BEGIN
    SELECT RAISE(ABORT, 'policy rules are immutable');
END;
CREATE TRIGGER IF NOT EXISTS policy_rules_immutable_delete
BEFORE DELETE ON policy_rules
BEGIN
    SELECT RAISE(ABORT, 'policy rules are immutable');
END;

-- A policy activation records why each current license state is held for
-- review or remains eligible. It never silently changes the license level.
CREATE TABLE IF NOT EXISTS policy_impacts (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    previous_version    INTEGER,
    next_version        INTEGER NOT NULL,
    task_class          TEXT NOT NULL,
    available_samples   INTEGER NOT NULL,
    required_samples    INTEGER NOT NULL,
    pass_rate           REAL NOT NULL,
    required_pass_rate  REAL NOT NULL,
    action              TEXT NOT NULL,
    reason              TEXT NOT NULL,
    created_at          TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_policy_impacts_version ON policy_impacts (next_version, task_class);
CREATE TRIGGER IF NOT EXISTS policy_impacts_immutable_update
BEFORE UPDATE ON policy_impacts
BEGIN
    SELECT RAISE(ABORT, 'policy impacts are immutable');
END;
CREATE TRIGGER IF NOT EXISTS policy_impacts_immutable_delete
BEFORE DELETE ON policy_impacts
BEGIN
    SELECT RAISE(ABORT, 'policy impacts are immutable');
END;

-- Only the hash of a server-issued tool authorization is stored. A conditional
-- update consumes it exactly once immediately before a side effect is written.
CREATE TABLE IF NOT EXISTS execution_permits (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    permit_digest   TEXT NOT NULL UNIQUE,
    policy_version  INTEGER NOT NULL,
    task_class      TEXT NOT NULL,
    tool            TEXT NOT NULL,
    order_id        TEXT NOT NULL,
    amount          REAL NOT NULL,
    actor_id        TEXT NOT NULL,
    issued_at       TEXT NOT NULL DEFAULT (datetime('now')),
    expires_at      TEXT NOT NULL,
    consumed_at     TEXT,
    disposition     TEXT NOT NULL DEFAULT 'issued'
);
CREATE INDEX IF NOT EXISTS idx_execution_permits_pending
    ON execution_permits (permit_digest, expires_at) WHERE consumed_at IS NULL;

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
    status      TEXT NOT NULL DEFAULT 'new',     -- new | done | waiting | declined | needs_info | needs_human | answered
    outcome     TEXT,                            -- one-line result for the inbox
    reply       TEXT,                            -- reply drafted for the customer
    steps       TEXT NOT NULL DEFAULT '[]',      -- JSON: the agent's steps
    run_id      INTEGER,
    trace_id    TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    handled_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_tickets_created ON tickets (created_at DESC);

-- Coding agents ------------------------------------------------------------
-- One license per (repository, action class): `npm test` earns `test-run` in
-- this repo only. Levels: 0 ask every time, 1 auto-allow command families a
-- person already approved here, 2 auto-allow the whole class.
CREATE TABLE IF NOT EXISTS agent_licenses (
    repo          TEXT NOT NULL,
    action_class  TEXT NOT NULL,
    level         INTEGER NOT NULL DEFAULT 0,
    successes     INTEGER NOT NULL DEFAULT 0,   -- verified outcomes at any level
    failures      INTEGER NOT NULL DEFAULT 0,
    successes_at_level INTEGER NOT NULL DEFAULT 0, -- since the last level change
    demoted_from  INTEGER,
    updated_at    TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (repo, action_class)
);

-- Command families a person approved in a repo (what level 1 auto-allows).
CREATE TABLE IF NOT EXISTS agent_patterns (
    repo          TEXT NOT NULL,
    action_class  TEXT NOT NULL,
    pattern       TEXT NOT NULL,
    approvals     INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (repo, pattern)
);

-- Every gate decision and what came of it.
CREATE TABLE IF NOT EXISTS agent_decisions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id    TEXT NOT NULL,
    agent         TEXT NOT NULL DEFAULT 'claude-code',
    turn_id       INTEGER,
    repo          TEXT NOT NULL,
    tool_name     TEXT NOT NULL,
    action_class  TEXT NOT NULL,
    pattern       TEXT NOT NULL,
    command       TEXT NOT NULL,
    decision      TEXT NOT NULL,                -- allow | ask | deny
    decided_by    TEXT NOT NULL,                -- license | person | hard-deny | classifier
    level         INTEGER NOT NULL,
    source        TEXT NOT NULL,                -- rules | jev | fallback
    reason        TEXT NOT NULL DEFAULT '',
    outcome       TEXT NOT NULL DEFAULT 'pending', -- pending | ran | verified | failed | denied | not-run
    trace_id      TEXT,
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_agent_decisions_session ON agent_decisions (session_id, id DESC);

-- One user prompt and the turn of work it started; verified at Stop.
CREATE TABLE IF NOT EXISTS agent_turns (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id    TEXT NOT NULL,
    agent         TEXT NOT NULL DEFAULT 'claude-code',
    repo          TEXT NOT NULL,
    cwd           TEXT NOT NULL,
    prompt        TEXT NOT NULL DEFAULT '',
    base_ref      TEXT,                         -- working tree snapshot at the prompt
    status        TEXT NOT NULL DEFAULT 'open', -- open | verified | blocked | failed
    scope_score   INTEGER,
    lines_changed INTEGER,
    files_changed INTEGER,
    tests         TEXT,                         -- passed | failed | none
    reason        TEXT,
    trace_id      TEXT,
    entire_checkpoint TEXT,                     -- last Entire checkpoint before a failure
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    closed_at     TEXT
);
CREATE INDEX IF NOT EXISTS idx_agent_turns_session ON agent_turns (session_id, id DESC);

-- Per-repository settings (the command that verifies a turn).
CREATE TABLE IF NOT EXISTS agent_repos (
    repo          TEXT PRIMARY KEY,
    path          TEXT NOT NULL,
    test_command  TEXT,
    last_tests    TEXT,                         -- passed | failed at the last turn check
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

-- This machine's coding policy, per repository or for all ("*"). It can only
-- tighten the built-in rules and the repository's .solo-license/policy.toml.
CREATE TABLE IF NOT EXISTS agent_policies (
    repo        TEXT PRIMARY KEY,
    body        TEXT NOT NULL,                  -- JSON: classes / deny / freeze
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Every change to a coding agent's license (promote | demote | restore | policy),
-- per repository and principal. Each row is also a commit in the license ledger.
CREATE TABLE IF NOT EXISTS agent_events (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    repo          TEXT NOT NULL,
    principal     TEXT NOT NULL DEFAULT 'main',  -- main | subagent:<type>
    action_class  TEXT NOT NULL,                 -- or 'policy' for a policy change
    kind          TEXT NOT NULL,
    from_level    INTEGER NOT NULL,
    to_level      INTEGER NOT NULL,
    reason        TEXT NOT NULL,
    actor_id      TEXT NOT NULL,
    git_sha       TEXT,
    trace_id      TEXT,                          -- the neatlogs trace that recorded the change
    entire_checkpoint TEXT,                      -- the agent's last Entire checkpoint, when known
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_agent_events_repo ON agent_events (repo, id DESC);

-- What the agent was told to undo. Sent with the hook answer (delivered_at
-- set) or queued for the session's next prompt (delivered_at NULL until then).
CREATE TABLE IF NOT EXISTS agent_remediations (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id    TEXT NOT NULL,
    turn_id       INTEGER,
    kind          TEXT NOT NULL,                 -- tool-failed | turn-failed | denied | flagged
    text          TEXT NOT NULL,
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    delivered_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_agent_remediations_session ON agent_remediations (session_id, delivered_at);

-- Rolling per-session fingerprints of tool calls (loop detection). Repeat
-- counters reset on every edit; 'edit:<turn>:<path>' rows count edits per file.
CREATE TABLE IF NOT EXISTS agent_fingerprints (
    session_id    TEXT NOT NULL,
    fingerprint   TEXT NOT NULL,
    count         INTEGER NOT NULL DEFAULT 0,
    failures      INTEGER NOT NULL DEFAULT 0,    -- consecutive failures with the same error
    last_outcome  TEXT,                          -- ok | failed
    last_error    TEXT,
    seq           INTEGER NOT NULL DEFAULT 0,    -- recency within the session window
    updated_at    TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (session_id, fingerprint)
);

-- A person said a decision or a turn was wrong. Its classes went back to L0
-- and the session's next prompt carries the remediation.
CREATE TABLE IF NOT EXISTS agent_flags (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    decision_id    INTEGER,
    turn_id        INTEGER,
    actor_id       TEXT NOT NULL,
    reason         TEXT NOT NULL,
    remediation_id INTEGER,                      -- the queued message for the agent
    created_at     TEXT NOT NULL DEFAULT (datetime('now')),
    delivered_at   TEXT
);
