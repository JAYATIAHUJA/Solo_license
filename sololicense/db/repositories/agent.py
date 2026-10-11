"""Coding-agent licenses, decisions and turns. The caller commits."""

from __future__ import annotations

import sqlite3


# --- licenses ----------------------------------------------------------------

def get_license(conn: sqlite3.Connection, repo: str, action_class: str) -> sqlite3.Row:
    conn.execute(
        "INSERT OR IGNORE INTO agent_licenses (repo, action_class) VALUES (?, ?)", (repo, action_class)
    )
    return conn.execute(
        "SELECT * FROM agent_licenses WHERE repo = ? AND action_class = ?", (repo, action_class)
    ).fetchone()


def list_licenses(conn: sqlite3.Connection, repo: str | None = None) -> list[sqlite3.Row]:
    if repo is None:
        return conn.execute("SELECT * FROM agent_licenses ORDER BY repo, action_class").fetchall()
    return conn.execute(
        "SELECT * FROM agent_licenses WHERE repo = ? ORDER BY action_class", (repo,)
    ).fetchall()


def add_evidence(conn: sqlite3.Connection, repo: str, action_class: str, *, ok: bool) -> None:
    get_license(conn, repo, action_class)  # create the row on first evidence
    change = ("successes = successes + 1, successes_at_level = successes_at_level + 1"
              if ok else "failures = failures + 1")
    conn.execute(
        f"UPDATE agent_licenses SET {change}, updated_at = datetime('now') "
        "WHERE repo = ? AND action_class = ?",
        (repo, action_class),
    )


def set_level(conn: sqlite3.Connection, repo: str, action_class: str, level: int,
              *, demoted_from: int | None = None) -> None:
    conn.execute(
        "UPDATE agent_licenses SET level = ?, demoted_from = ?, successes_at_level = 0, "
        "updated_at = datetime('now') "
        "WHERE repo = ? AND action_class = ?",
        (level, demoted_from, repo, action_class),
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

def insert_decision(conn: sqlite3.Connection, **fields) -> int:
    keys = ", ".join(fields)
    marks = ", ".join("?" for _ in fields)
    cur = conn.execute(f"INSERT INTO agent_decisions ({keys}) VALUES ({marks})", tuple(fields.values()))
    return int(cur.lastrowid)


def pending_decision(conn: sqlite3.Connection, session_id: str, tool_name: str, command: str) -> sqlite3.Row | None:
    """The latest gate decision this tool run belongs to (PermissionRequest
    carries no tool_use_id, so the session, tool and command identify it)."""
    return conn.execute(
        """
        SELECT * FROM agent_decisions
         WHERE session_id = ? AND tool_name = ? AND command = ? AND outcome = 'pending'
         ORDER BY id DESC LIMIT 1
        """,
        (session_id, tool_name, command),
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
              base_ref: str | None, trace_id: str | None) -> int:
    cur = conn.execute(
        "INSERT INTO agent_turns (session_id, repo, cwd, prompt, base_ref, trace_id) VALUES (?, ?, ?, ?, ?, ?)",
        (session_id, repo, cwd, prompt, base_ref, trace_id),
    )
    return int(cur.lastrowid)


def current_turn(conn: sqlite3.Connection, session_id: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM agent_turns WHERE session_id = ? ORDER BY id DESC LIMIT 1", (session_id,)
    ).fetchone()


def close_turn(conn: sqlite3.Connection, turn_id: int, **fields) -> None:
    sets = ", ".join(f"{k} = ?" for k in fields)
    conn.execute(f"UPDATE agent_turns SET {sets}, closed_at = datetime('now') WHERE id = ?",
                 (*fields.values(), turn_id))


def set_checkpoint(conn: sqlite3.Connection, turn_id: int, checkpoint_id: str) -> None:
    conn.execute("UPDATE agent_turns SET entire_checkpoint = ? WHERE id = ?", (checkpoint_id, turn_id))


def get_turn(conn: sqlite3.Connection, turn_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM agent_turns WHERE id = ?", (turn_id,)).fetchone()


def recent_turns(conn: sqlite3.Connection, limit: int = 30) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM agent_turns ORDER BY id DESC LIMIT ?", (limit,)).fetchall()


# --- repositories ------------------------------------------------------------

def ensure_repo(conn: sqlite3.Connection, repo: str, path: str) -> sqlite3.Row:
    conn.execute("INSERT OR IGNORE INTO agent_repos (repo, path) VALUES (?, ?)", (repo, path))
    return conn.execute("SELECT * FROM agent_repos WHERE repo = ?", (repo,)).fetchone()


def set_test_command(conn: sqlite3.Connection, repo: str, command: str | None) -> None:
    conn.execute("UPDATE agent_repos SET test_command = ? WHERE repo = ?", (command or None, repo))
