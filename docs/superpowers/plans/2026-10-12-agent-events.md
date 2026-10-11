# Agent events (PR 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Coding license changes are stored in their own `agent_events` table, so the payments tables (and `license_events`' foreign key to `runs`) can be removed in PR 2.

**Architecture:** Add `agent_events` to `schema.sql`, give `db/repositories/agent.py` three event functions, point `CodingGate._change` / `record_policy` at them, copy old coding rows from `license_events` once on startup, and keep the dashboard's `events` list in its current shape so `Ledger.jsx` needs no change yet.

**Tech Stack:** Python 3.11+, stdlib `sqlite3`, FastAPI, pytest.

## Global Constraints

- `agent_events` columns: repo, principal, action_class, kind, from_level, to_level, reason, actor_id, git_sha, created_at (PRD F1 data migration). No foreign key to `runs`.
- `principal` defaults to `'main'` (PRD §4).
- Old SQLite files keep working: `apply_schema` only creates; refund tables are ignored, not dropped.
- Branch `feat/agent-events`; PR title `feat(coding): coding license changes get their own event table`.

---

### Task 1: The table and its repository functions, used by the gate

**Files:**
- Modify: `sololicense/db/schema.sql` (append after `agent_policies`)
- Modify: `sololicense/db/repositories/agent.py` (new `# --- events` section)
- Modify: `sololicense/coding/gate.py` (`_change`, `record_policy`, imports)
- Modify: `scripts/coding_demo.py:206-207`
- Test: `tests/test_coding_gate.py`, `tests/test_coding_verify.py:129`, `tests/test_coding_policy.py:146`

**Interfaces:**
- Produces:
  - `agent_repo.insert_event(conn, *, repo: str, action_class: str, kind: str, from_level: int, to_level: int, reason: str, actor_id: str, principal: str = "main") -> int`
  - `agent_repo.set_event_sha(conn, event_id: int, git_sha: str) -> None`
  - `agent_repo.list_events(conn, repo: str | None = None, limit: int = 60) -> list[sqlite3.Row]` (newest first)

- [ ] **Step 1: Write the failing test** (append to `tests/test_coding_gate.py`)

```python
def test_every_license_change_is_an_agent_event_with_its_commit(gate):
    gate.user_prompt(_event(gate, prompt="x"))
    for _ in range(3):
        _approve_and_run(gate, "npm test")
    event = gate.conn.execute("SELECT * FROM agent_events ORDER BY id DESC LIMIT 1").fetchone()
    assert (event["repo"], event["principal"], event["action_class"], event["kind"]) == \
        ("shop-api", "main", "test-run", "promote")
    assert (event["from_level"], event["to_level"]) == (0, 1)
    assert event["actor_id"] == "system:coding-gate" and event["git_sha"]
    assert gate.conn.execute(
        "SELECT COUNT(*) FROM license_events WHERE task_class LIKE '%@%'").fetchone()[0] == 0
```

And in `test_a_person_resumes_a_paused_class_within_its_ceiling` replace the last two lines with:

```python
    event = gate.conn.execute("SELECT * FROM agent_events ORDER BY id DESC LIMIT 1").fetchone()
    assert event["kind"] == "restore" and event["actor_id"] == "human:jayati"
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_coding_gate.py -q`
Expected: FAIL with `sqlite3.OperationalError: no such table: agent_events`

- [ ] **Step 3: Implement**

`schema.sql`, appended:

```sql
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
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_agent_events_repo ON agent_events (repo, id DESC);
```

`agent.py`, new section before `# --- repositories`:

```python
# --- events ------------------------------------------------------------------

def insert_event(conn: sqlite3.Connection, *, repo: str, action_class: str, kind: str, from_level: int,
                 to_level: int, reason: str, actor_id: str, principal: str = "main") -> int:
    cur = conn.execute(
        "INSERT INTO agent_events (repo, principal, action_class, kind, from_level, to_level, reason, actor_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (repo, principal, action_class, kind, from_level, to_level, reason, actor_id),
    )
    return int(cur.lastrowid)


def set_event_sha(conn: sqlite3.Connection, event_id: int, git_sha: str) -> None:
    conn.execute("UPDATE agent_events SET git_sha = ? WHERE id = ?", (git_sha, event_id))


def list_events(conn: sqlite3.Connection, repo: str | None = None, limit: int = 60) -> list[sqlite3.Row]:
    if repo is None:
        return conn.execute("SELECT * FROM agent_events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return conn.execute(
        "SELECT * FROM agent_events WHERE repo = ? ORDER BY id DESC LIMIT ?", (repo, limit)
    ).fetchall()
```

`gate.py`: drop `from sololicense.db.repositories import events as events_repo`; `record_policy` and `_change` become:

```python
    def record_policy(self, repo: str, summary: str, actor_id: str) -> str | None:
        """A policy change on this machine: an event and a ledger commit."""
        event_id = agent_repo.insert_event(self.conn, repo=repo, action_class="policy", kind="policy",
                                           from_level=0, to_level=0, reason=summary, actor_id=actor_id)
        sha = self.ledger.record(LedgerEntry(f"policy@{repo}", "policy", 0, 0, summary, None, None))
        if sha:
            agent_repo.set_event_sha(self.conn, event_id, sha)
        return sha

    def _change(self, repo: str, key: str, kind: str, old: int, new: int, reason: str, trace: Trace,
                actor_id: str = GATE_ACTOR) -> None:
        agent_repo.set_level(self.conn, repo, key, new, demoted_from=old if kind == "demote" else None)
        event_id = agent_repo.insert_event(self.conn, repo=repo, action_class=key, kind=kind,
                                           from_level=old, to_level=new, reason=reason, actor_id=actor_id)
        sha = self.ledger.record(LedgerEntry(f"{key}@{repo}", kind, old, new, reason, None, trace.trace_id))
        if sha:
            agent_repo.set_event_sha(self.conn, event_id, sha)
        trace.span(f"license.{kind}", status="error" if kind == "demote" else "ok", action_class=key,
                   repo=repo, from_level=old, to_level=new, reason=reason, git_sha=sha or "")
```

Other readers of the old table:
- `tests/test_coding_verify.py:129` -> `SELECT reason FROM agent_events ORDER BY id DESC LIMIT 1`
- `tests/test_coding_policy.py:146` -> `SELECT reason FROM agent_events WHERE kind = 'policy'`
- `scripts/coding_demo.py:206-207` -> `SELECT action_class || '@' || repo AS task_class, kind, from_level, to_level, git_sha FROM agent_events ORDER BY id`

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_coding_gate.py tests/test_coding_verify.py tests/test_coding_policy.py tests/unit/test_coding_demo.py -q`
Expected: all pass

- [ ] **Step 5: Commit**

```powershell
git add sololicense/db/schema.sql sololicense/db/repositories/agent.py sololicense/coding/gate.py scripts/coding_demo.py tests/test_coding_gate.py tests/test_coding_verify.py tests/test_coding_policy.py
git commit -m "feat(coding): coding license changes are recorded in agent_events"
```

---

### Task 2: Copy old coding events once, on startup

**Files:**
- Modify: `sololicense/db/database.py` (`apply_schema`, new `_migrate_v3`)
- Test: `tests/unit/test_agent_events_migration.py` (new)

**Interfaces:**
- Consumes: `agent_events` table from Task 1.
- Produces: `_migrate_v3(conn)` - private; called by `apply_schema`.

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/unit/test_agent_events_migration.py -q`
Expected: FAIL - `rows == []`

- [ ] **Step 3: Implement** (`database.py`)

```python
def apply_schema(conn: sqlite3.Connection) -> None:
    """Create every table/index if absent. Safe to call on every startup."""
    conn.executescript(_SCHEMA_PATH.read_text(encoding="utf-8"))
    _migrate_runs(conn)
    _migrate_v3(conn)
    conn.commit()


def _migrate_v3(conn: sqlite3.Connection) -> None:
    """Coding events used to share ``license_events`` with the payments agent
    (as ``<class>@<repo>``). Copy them into ``agent_events`` the first time."""
    if conn.execute("SELECT 1 FROM agent_events LIMIT 1").fetchone():
        return
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'license_events'").fetchone():
        return
    conn.execute(
        """
        INSERT INTO agent_events (repo, action_class, kind, from_level, to_level, reason, actor_id, git_sha, created_at)
        SELECT substr(task_class, instr(task_class, '@') + 1), substr(task_class, 1, instr(task_class, '@') - 1),
               kind, from_level, to_level, reason, actor_id, git_sha, created_at
          FROM license_events WHERE task_class LIKE '%@%' ORDER BY id
        """
    )
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/unit/test_agent_events_migration.py -q`
Expected: 1 passed

- [ ] **Step 5: Commit**

```powershell
git add sololicense/db/database.py tests/unit/test_agent_events_migration.py
git commit -m "feat(coding): copy old coding events into agent_events on startup"
```

---

### Task 3: The API serves the new events

**Files:**
- Modify: `sololicense/api/app.py` (`_observability`, `dashboard_payload` events, `coding_payload`)
- Test: `tests/test_coding_gate.py`

**Interfaces:**
- Consumes: `agent_repo.list_events` from Task 1.
- Produces: `/api/coding` -> `"events": list[dict]` (agent_events rows); `/api/dashboard` -> `events` mixes refund rows and coding rows as `{**row, "id": "agent-<id>", "task_class": "<class>@<repo>"}`, newest first, max 60.

- [ ] **Step 1: Write the failing test** (append to `tests/test_coding_gate.py`)

```python
def test_the_coding_dashboard_lists_license_events(gate, harness, tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from sololicense.api import app as app_module
    from sololicense.db.database import init_db

    conn = init_db(tmp_path / "events.db", check_same_thread=False)
    threaded = CodingGate(conn, harness.worker._tracer, GitLedger(repo_root=harness.repo),
                          jev_client=JevClient(), checkpoint_lookup=lambda cwd, session: None)
    agent_repo.ensure_repo(conn, "shop-api", str(gate.project))
    threaded.restore("shop-api", "test-run", 1, actor_id="human:jayati", reason="reviewed")

    class Ctx:
        coding_gate = threaded

    Ctx.conn = conn
    monkeypatch.setattr(app_module, "get_context", lambda: Ctx)
    events = TestClient(app_module.app).get("/api/coding?repo=shop-api").json()["events"]
    assert [(e["action_class"], e["kind"], e["to_level"]) for e in events] == [("test-run", "restore", 1)]
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_coding_gate.py::test_the_coding_dashboard_lists_license_events -q`
Expected: FAIL with `KeyError: 'events'`

- [ ] **Step 3: Implement** (`app.py`)

In `coding_payload`'s returned dict, after `"turns": turns,`:

```python
        "events": [dict(r) for r in agent_repo.list_events(context.conn, repo, 60)],
```

In `dashboard_payload`, replace the `events = [...license_events...]` block:

```python
    events = [dict(e) for e in context.conn.execute(
        "SELECT * FROM license_events WHERE task_class NOT LIKE '%@%' ORDER BY id DESC LIMIT 60")]
    events += [{**dict(e), "id": f"agent-{e['id']}", "task_class": f"{e['action_class']}@{e['repo']}"}
               for e in agent_repo.list_events(context.conn, limit=60)]
    events = sorted(events, key=lambda e: e["created_at"], reverse=True)[:60]
```

In `_observability`, replace the ledger query:

```python
    ledger = context.conn.execute(
        """SELECT (SELECT COUNT(*) FROM license_events WHERE task_class NOT LIKE '%@%')
                  + (SELECT COUNT(*) FROM agent_events) AS n,
                  (SELECT COUNT(git_sha) FROM license_events WHERE task_class NOT LIKE '%@%')
                  + (SELECT COUNT(git_sha) FROM agent_events) AS committed"""
    ).fetchone()
```

- [ ] **Step 4: Run the whole suite**

Run: `python -m pytest -q`
Expected: all pass

- [ ] **Step 5: Commit, push, open the PR**

```powershell
git add sololicense/api/app.py tests/test_coding_gate.py
git commit -m "feat(coding): the dashboard serves coding license events from agent_events"
git push -u origin feat/agent-events
gh pr create --base main --title "feat(coding): coding license changes get their own event table" --body-file <notes>
```
