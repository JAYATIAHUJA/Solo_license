"""Coding-agent licenses, decisions and turns. The caller commits."""

from __future__ import annotations

import sqlite3


# --- licenses ----------------------------------------------------------------

def get_license(conn: sqlite3.Connection, repo: str, action_class: str, *, principal: str = "main") -> sqlite3.Row:
    conn.execute(
        "INSERT OR IGNORE INTO agent_licenses (repo, principal, action_class) VALUES (?, ?, ?)",
        (repo, principal, action_class),
    )
    return conn.execute(
        "SELECT * FROM agent_licenses WHERE repo = ? AND principal = ? AND action_class = ?",
        (repo, principal, action_class),
    ).fetchone()


def effective_license(conn: sqlite3.Connection, repo: str, action_class: str, principal: str,
                     *, max_level: int = 1, create: bool = True) -> dict:
    """Return a principal's license, inheriting the repo license at a ceiling.

    Main-agent rows are the source of truth for the repository. A subagent gets
    its own row once it has evidence; before that, it inherits the main row but
    can never exceed ``max_level``.
    """
    if principal == "main":
        row = conn.execute(
            "SELECT * FROM agent_licenses WHERE repo = ? AND principal = 'main' AND action_class = ?",
            (repo, action_class),
        ).fetchone()
        if row is not None:
            return dict(row)
        if create:
            return dict(get_license(conn, repo, action_class))
        return {"repo": repo, "principal": "main", "action_class": action_class,
                "level": 0, "successes": 0, "failures": 0, "successes_at_level": 0,
                "demoted_from": None, "updated_at": None}
    row = conn.execute(
        "SELECT * FROM agent_licenses WHERE repo = ? AND principal = ? AND action_class = ?",
        (repo, principal, action_class),
    ).fetchone()
    if row is not None:
        result = dict(row)
        result["level"] = min(int(result["level"]), max_level)
        return result
    inherited_row = conn.execute(
        "SELECT * FROM agent_licenses WHERE repo = ? AND principal = 'main' AND action_class = ?",
        (repo, action_class),
    ).fetchone()
    if inherited_row is None and create:
        inherited_row = get_license(conn, repo, action_class, principal="main")
    inherited = dict(inherited_row) if inherited_row is not None else {
        "repo": repo, "principal": "main", "action_class": action_class,
        "level": 0, "successes": 0, "failures": 0, "successes_at_level": 0,
        "demoted_from": None, "updated_at": None,
    }
    inherited["principal"] = principal
    inherited["level"] = min(int(inherited["level"]), max_level)
    return inherited


def list_licenses(conn: sqlite3.Connection, repo: str | None = None) -> list[sqlite3.Row]:
    if repo is None:
        return conn.execute("SELECT * FROM agent_licenses ORDER BY repo, principal, action_class").fetchall()
    return conn.execute(
        "SELECT * FROM agent_licenses WHERE repo = ? ORDER BY principal, action_class", (repo,)
    ).fetchall()


def add_evidence(conn: sqlite3.Connection, repo: str, action_class: str, *, ok: bool,
                 principal: str = "main") -> None:
    get_license(conn, repo, action_class, principal=principal)  # create the row on first evidence
    change = ("successes = successes + 1, successes_at_level = successes_at_level + 1"
              if ok else "failures = failures + 1")
    conn.execute(
        f"UPDATE agent_licenses SET {change}, updated_at = datetime('now') "
        "WHERE repo = ? AND principal = ? AND action_class = ?",
        (repo, principal, action_class),
    )


def set_level(conn: sqlite3.Connection, repo: str, action_class: str, level: int,
              *, demoted_from: int | None = None, principal: str = "main") -> None:
    conn.execute(
        "UPDATE agent_licenses SET level = ?, demoted_from = ?, successes_at_level = 0, "
        "updated_at = datetime('now') "
        "WHERE repo = ? AND principal = ? AND action_class = ?",
        (level, demoted_from, repo, principal, action_class),
    )


# --- approved command families --------------------------------------------------

def approve_pattern(conn: sqlite3.Connection, repo: str, action_class: str, pattern: str) -> None:
    conn.execute(
        """
        INSERT INTO agent_patterns (repo, action_class, pattern, approvals) VALUES (?, ?, ?, 1)
        ON CONFLICT (repo, pattern) DO UPDATE SET approvals = approvals + 1
        """,
        (repo, action_class, pattern),
    )


def pattern_approved(conn: sqlite3.Connection, repo: str, pattern: str) -> bool:
    row = conn.execute(
        "SELECT approvals FROM agent_patterns WHERE repo = ? AND pattern = ?", (repo, pattern)
    ).fetchone()
    return bool(row and row["approvals"] > 0)


def forget_patterns(conn: sqlite3.Connection, repo: str, action_class: str) -> None:
    conn.execute("DELETE FROM agent_patterns WHERE repo = ? AND action_class = ?", (repo, action_class))


# --- decisions -------------------------------------------------------------

DECISION_COLUMNS = frozenset({
    "session_id", "agent", "principal", "turn_id", "repo", "tool_name", "action_class", "pattern", "command",
    "decision", "decided_by", "level", "source", "reason", "outcome", "trace_id",
})


def insert_decision(conn: sqlite3.Connection, **fields) -> int:
    """Column names come only from this fixed list; values are always bound."""
    unknown = set(fields) - DECISION_COLUMNS
    if unknown:
        raise ValueError(f"unknown agent_decisions columns: {sorted(unknown)}")
    keys = ", ".join(fields)
    marks = ", ".join("?" for _ in fields)
    cur = conn.execute(f"INSERT INTO agent_decisions ({keys}) VALUES ({marks})", tuple(fields.values()))
    return int(cur.lastrowid)


def pending_decision(conn: sqlite3.Connection, session_id: str, tool_name: str, command: str,
                     *, principal: str = "main") -> sqlite3.Row | None:
    """The latest gate decision this tool run belongs to (PermissionRequest
    carries no tool_use_id, so the session, tool and command identify it)."""
    return conn.execute(
        """
        SELECT * FROM agent_decisions
         WHERE session_id = ? AND principal = ? AND tool_name = ? AND command = ? AND outcome = 'pending'
         ORDER BY id DESC LIMIT 1
        """,
        (session_id, principal, tool_name, command),
    ).fetchone()


def set_outcome(conn: sqlite3.Connection, decision_id: int, outcome: str, *, decided_by: str | None = None) -> None:
    if decided_by:
        conn.execute("UPDATE agent_decisions SET outcome = ?, decided_by = ? WHERE id = ?",
                     (outcome, decided_by, decision_id))
    else:
        conn.execute("UPDATE agent_decisions SET outcome = ? WHERE id = ?", (outcome, decision_id))


def decisions_for_turn(conn: sqlite3.Connection, turn_id: int) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM agent_decisions WHERE turn_id = ? ORDER BY id", (turn_id,)).fetchall()


def recent_decisions(conn: sqlite3.Connection, limit: int = 50) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM agent_decisions ORDER BY id DESC LIMIT ?", (limit,)).fetchall()


# --- turns ---------------------------------------------------------------

def open_turn(conn: sqlite3.Connection, *, session_id: str, repo: str, cwd: str, prompt: str,
              base_ref: str | None, trace_id: str | None, agent: str = "claude-code",
              principal: str = "main") -> int:
    cur = conn.execute(
        "INSERT INTO agent_turns (session_id, agent, principal, repo, cwd, prompt, base_ref, trace_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (session_id, agent, principal, repo, cwd, prompt, base_ref, trace_id),
    )
    return int(cur.lastrowid)


def current_turn(conn: sqlite3.Connection, session_id: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM agent_turns WHERE session_id = ? ORDER BY id DESC LIMIT 1", (session_id,)
    ).fetchone()


TURN_CLOSE_COLUMNS = frozenset({"status", "reason", "scope_score", "lines_changed", "files_changed", "tests"})


def close_turn(conn: sqlite3.Connection, turn_id: int, **fields) -> None:
    """Column names come only from this fixed list; values are always bound."""
    unknown = set(fields) - TURN_CLOSE_COLUMNS
    if unknown:
        raise ValueError(f"unknown agent_turns columns: {sorted(unknown)}")
    sets = ", ".join(f"{k} = ?" for k in fields)
    conn.execute(f"UPDATE agent_turns SET {sets}, closed_at = datetime('now') WHERE id = ?",
                 (*fields.values(), turn_id))


def note_block(conn: sqlite3.Connection, turn_id: int, reason: str) -> None:
    """Remember why a turn was sent back; it stays open to be checked again."""
    conn.execute("UPDATE agent_turns SET reason = ?, scope_score = scope_score WHERE id = ?", (reason, turn_id))


def set_checkpoint(conn: sqlite3.Connection, turn_id: int, checkpoint_id: str) -> None:
    conn.execute("UPDATE agent_turns SET entire_checkpoint = ? WHERE id = ?", (checkpoint_id, turn_id))


def get_turn(conn: sqlite3.Connection, turn_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM agent_turns WHERE id = ?", (turn_id,)).fetchone()


def agents_seen(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Each coding agent that has called the gate, and when it last did."""
    return conn.execute(
        "SELECT agent, COUNT(*) AS decisions, MAX(created_at) AS last_seen "
        "FROM agent_decisions GROUP BY agent ORDER BY last_seen DESC"
    ).fetchall()


def recent_turns(conn: sqlite3.Connection, limit: int = 30) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM agent_turns ORDER BY id DESC LIMIT ?", (limit,)).fetchall()


# --- events ------------------------------------------------------------------

def insert_event(conn: sqlite3.Connection, *, repo: str, action_class: str, kind: str, from_level: int,
                 to_level: int, reason: str, actor_id: str, principal: str = "main",
                 trace_id: str | None = None, entire_checkpoint: str | None = None) -> int:
    cur = conn.execute(
        "INSERT INTO agent_events (repo, principal, action_class, kind, from_level, to_level, reason, actor_id, "
        "trace_id, entire_checkpoint) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (repo, principal, action_class, kind, from_level, to_level, reason, actor_id, trace_id, entire_checkpoint),
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


# --- remediations --------------------------------------------------------------

def queue_remediation(conn: sqlite3.Connection, *, session_id: str, turn_id: int | None, kind: str, text: str,
                      delivered: bool = False) -> int:
    cur = conn.execute(
        "INSERT INTO agent_remediations (session_id, turn_id, kind, text, delivered_at) "
        "VALUES (?, ?, ?, ?, CASE WHEN ? THEN datetime('now') END)",
        (session_id, turn_id, kind, text, int(delivered)),
    )
    return int(cur.lastrowid)


def take_remediations(conn: sqlite3.Connection, session_id: str) -> list[sqlite3.Row]:
    """The session's queued remediations, oldest first, marked delivered."""
    rows = conn.execute(
        "SELECT * FROM agent_remediations WHERE session_id = ? AND delivered_at IS NULL ORDER BY id", (session_id,)
    ).fetchall()
    if rows:
        ids = [(r["id"],) for r in rows]
        conn.executemany("UPDATE agent_remediations SET delivered_at = datetime('now') WHERE id = ?", ids)
        conn.executemany("UPDATE agent_flags SET delivered_at = datetime('now') WHERE remediation_id = ?", ids)
    return rows


def recent_remediations(conn: sqlite3.Connection, limit: int = 30) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM agent_remediations ORDER BY id DESC LIMIT ?", (limit,)).fetchall()


# --- flags --------------------------------------------------------------------

def get_decision(conn: sqlite3.Connection, decision_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM agent_decisions WHERE id = ?", (decision_id,)).fetchone()


def insert_flag(conn: sqlite3.Connection, *, decision_id: int | None, turn_id: int | None, actor_id: str,
                reason: str, remediation_id: int | None) -> int:
    cur = conn.execute(
        "INSERT INTO agent_flags (decision_id, turn_id, actor_id, reason, remediation_id) VALUES (?, ?, ?, ?, ?)",
        (decision_id, turn_id, actor_id, reason, remediation_id),
    )
    return int(cur.lastrowid)


def list_flags(conn: sqlite3.Connection, limit: int = 30) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM agent_flags ORDER BY id DESC LIMIT ?", (limit,)).fetchall()


# --- repositories ------------------------------------------------------------

def ensure_repo(conn: sqlite3.Connection, repo: str, path: str) -> sqlite3.Row:
    conn.execute("INSERT OR IGNORE INTO agent_repos (repo, path) VALUES (?, ?)", (repo, path))
    return conn.execute("SELECT * FROM agent_repos WHERE repo = ?", (repo,)).fetchone()


def set_last_tests(conn: sqlite3.Connection, repo: str, result: str) -> None:
    conn.execute("UPDATE agent_repos SET last_tests = ? WHERE repo = ?", (result, repo))


def set_test_command(conn: sqlite3.Connection, repo: str, command: str | None) -> None:
    conn.execute("UPDATE agent_repos SET test_command = ? WHERE repo = ?", (command or None, repo))
