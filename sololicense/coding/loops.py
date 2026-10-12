"""Loop and stuck detection (PRD F9).

Every tool call the gate sees after it ran (PostToolUse fires for every call;
PermissionRequest only when the agent would prompt) is fingerprinted: the tool
plus its normalised arguments. A call counts as a *repeat* only while nothing
was edited in between - running ``npm test`` after each fix is work, running
it again on an unchanged tree is a loop. So any file edit resets the session's
repeat counters.

* ``WARN_AT`` identical calls     -> guidance next to the tool result;
* ``STOP_AT``                     -> denied with ``interrupt`` at the prompt, or
                                     a halt after the run when nobody was asked,
                                     and every later call is refused until the
                                     turn ends or the person prompts again;
* the same failure ``SAME_FAILURE_AT`` times in a row -> "stop retrying";
* one file edited ``THRASH_AT`` times in a turn -> the turn is sent back once.

None of this changes a license: it is guidance and halts, not evidence.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass

from sololicense.coding.actions import edited_path

WINDOW = 20             # distinct calls remembered per session
WARN_AT = 3
STOP_AT = 5
SAME_FAILURE_AT = 3
THRASH_AT = 4

_HALT = "halt"
# Repeat counters; 'edit:<turn>:<path>' bookkeeping and the halt outlive edits and the window.
_COUNTERS = f"fingerprint NOT GLOB 'edit:*' AND fingerprint != '{_HALT}'"
_SHELL = {"Bash", "PowerShell"}
_EDITS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
_VOLATILE = (
    (re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:?\d{2})?"), "<time>"),
    (re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I), "<uuid>"),
    (re.compile(r"\b[0-9a-f]{12,}\b", re.I), "<hex>"),
    (re.compile(r"\b\d{6,}\b"), "<n>"),
)


def normalise(text: str) -> str:
    """Whitespace collapsed; timestamps, ids and long numbers blanked."""
    text = " ".join(str(text).split())
    for pattern, blank in _VOLATILE:
        text = pattern.sub(blank, text)
    return text


def fingerprint(tool: str, tool_input: dict) -> str:
    tool_input = tool_input if isinstance(tool_input, dict) else {}
    if tool in _SHELL:
        key = str(tool_input.get("command", ""))
    elif tool in _EDITS:
        key = "\n".join([edited_path(tool_input), *(str(tool_input.get(k, "")) for k in (
            "old_string", "new_string", "content", "edits", "cell_id", "new_source", "cell_type", "edit_mode"))])
    else:  # descriptions and timeouts vary between otherwise identical calls
        key = json.dumps({k: v for k, v in tool_input.items() if k not in ("description", "timeout")},
                         sort_keys=True, default=str)
    return f"{tool}:" + hashlib.sha1(normalise(key).encode("utf-8")).hexdigest()[:16]


def error_head(error: str) -> str:
    """The first line of a failure that says why (not ``Exit code N``)."""
    lines = [line.strip() for line in str(error or "").splitlines() if line.strip()]
    useful = [line for line in lines if not re.fullmatch(r"Exit code -?\d+", line)]
    return normalise((useful or lines or [""])[0])[:200]


def is_edit(tool: str) -> bool:
    return tool in _EDITS


@dataclass(frozen=True)
class Seen:
    count: int          # identical calls since the last edit
    failures: int       # consecutive failures with the same error
    error: str


def seen(conn: sqlite3.Connection, session_id: str, fp: str) -> Seen:
    row = conn.execute("SELECT count, failures, last_error FROM agent_fingerprints "
                       "WHERE session_id = ? AND fingerprint = ?", (session_id, fp)).fetchone()
    return Seen(row["count"], row["failures"], row["last_error"] or "") if row else Seen(0, 0, "")


def record(conn: sqlite3.Connection, session_id: str, fp: str, *, failed: bool, error: str = "") -> Seen:
    """Count one call that ran. The caller commits."""
    before = seen(conn, session_id, fp)
    head = error_head(error) if failed else ""
    failures = (before.failures + 1 if head == before.error else 1) if failed else 0
    conn.execute(
        """
        INSERT INTO agent_fingerprints (session_id, fingerprint, count, failures, last_outcome, last_error, seq)
        VALUES (?, ?, 1, ?, ?, ?, (SELECT COALESCE(MAX(seq), 0) + 1 FROM agent_fingerprints))
        ON CONFLICT (session_id, fingerprint) DO UPDATE SET
            count = count + 1, failures = excluded.failures, last_outcome = excluded.last_outcome,
            last_error = excluded.last_error, seq = excluded.seq, updated_at = datetime('now')
        """,
        (session_id, fp, failures, "failed" if failed else "ok", head),
    )
    conn.execute(
        f"""
        DELETE FROM agent_fingerprints WHERE session_id = ? AND {_COUNTERS}
           AND fingerprint NOT IN (SELECT fingerprint FROM agent_fingerprints
                                    WHERE session_id = ? AND {_COUNTERS}
                                    ORDER BY seq DESC LIMIT ?)
        """,
        (session_id, session_id, WINDOW),
    )
    return seen(conn, session_id, fp)


def record_edit(conn: sqlite3.Connection, session_id: str, turn_id: int | None, path: str) -> None:
    """An edit: repeat counters start over, and the file's edits this turn grow
    (earlier turns' counts are dropped: only the open turn is checked)."""
    conn.execute(f"DELETE FROM agent_fingerprints WHERE session_id = ? AND {_COUNTERS}", (session_id,))
    if turn_id is not None:
        conn.execute("DELETE FROM agent_fingerprints WHERE session_id = ? AND fingerprint GLOB 'edit:*' "
                     "AND fingerprint NOT GLOB ?", (session_id, f"edit:{int(turn_id)}:*"))
    if turn_id is not None and path:
        record(conn, session_id, f"edit:{turn_id}:{path}", failed=False)


def thrashed(conn: sqlite3.Connection, session_id: str, turn_id: int) -> list[tuple[str, int]]:
    """Files edited at least ``THRASH_AT`` times in this turn, with their counts."""
    prefix = f"edit:{turn_id}:"
    rows = conn.execute(
        "SELECT fingerprint, count FROM agent_fingerprints WHERE session_id = ? AND substr(fingerprint, 1, ?) = ? "
        "AND count >= ? ORDER BY count DESC",
        (session_id, len(prefix), prefix, THRASH_AT),
    ).fetchall()
    return [(r["fingerprint"][len(prefix):], int(r["count"])) for r in rows]


def halt(conn: sqlite3.Connection, session_id: str, reason: str) -> None:
    """The session hit ``STOP_AT``: every call it makes is refused until the turn ends."""
    conn.execute(
        """
        INSERT INTO agent_fingerprints (session_id, fingerprint, count, last_error) VALUES (?, ?, 1, ?)
        ON CONFLICT (session_id, fingerprint) DO UPDATE SET last_error = excluded.last_error,
            updated_at = datetime('now')
        """,
        (session_id, _HALT, reason),
    )


def halted(conn: sqlite3.Connection, session_id: str) -> str:
    """Why the session was stopped, or "" if it was not."""
    row = conn.execute("SELECT last_error FROM agent_fingerprints WHERE session_id = ? AND fingerprint = ?",
                       (session_id, _HALT)).fetchone()
    return row["last_error"] or "" if row else ""


def clear_halt(conn: sqlite3.Connection, session_id: str) -> None:
    conn.execute("DELETE FROM agent_fingerprints WHERE session_id = ? AND fingerprint = ?", (session_id, _HALT))
