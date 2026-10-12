"""Bounded session context supplied to Jev and the coding dashboard."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from typing import Any

MAX_CHARS = 20_000  # comfortably below Jev's 32k state budget


def _args_digest(command: str) -> str:
    return hashlib.sha256(str(command).encode("utf-8")).hexdigest()[:12]


def _turn_so_far(conn: sqlite3.Connection, turn: sqlite3.Row | None) -> dict:
    """What this turn has done so far: the files it edited, how big the change
    is once checked, and the calls that failed (names and outcomes only)."""
    if turn is None:
        return {"files_touched": [], "diff_stat": "", "failures": []}
    rows = conn.execute("SELECT tool_name, command, action_class, outcome FROM agent_decisions "
                        "WHERE turn_id = ? ORDER BY id", (turn["id"],)).fetchall()
    files = []
    for row in rows:
        if row["action_class"] == "file-edit":
            command = str(row["command"])
            edit_tool = row["tool_name"] in ("Edit", "Write", "MultiEdit", "NotebookEdit")
            target = (command.split(" ", 1)[-1] if edit_tool else command).strip()[:200]
            if target and target not in files:
                files.append(target)
    failures = [str(row["command"])[:120] for row in rows if row["outcome"] == "failed"][-8:]
    stat = ""
    if turn["lines_changed"] is not None:
        stat = f"{turn['lines_changed']} lines in {turn['files_changed']} files"
    return {"files_touched": files[:20], "diff_stat": stat, "failures": failures}


def build(conn: sqlite3.Connection, session_id: str, *, repo: str = "", principal: str = "main",
          current_call: dict[str, Any] | None = None) -> dict:
    """Build a stable, JSON-serialisable digest for one active session."""
    turn = conn.execute(
        "SELECT * FROM agent_turns WHERE session_id = ? AND principal = ? ORDER BY id DESC LIMIT 1",
        (session_id, principal),
    ).fetchone()
    resolved_repo = repo or (str(turn["repo"]) if turn else "")
    calls = conn.execute(
        "SELECT tool_name, command, outcome FROM agent_decisions "
        "WHERE session_id = ? AND principal = ? ORDER BY id DESC LIMIT 12",
        (session_id, principal),
    ).fetchall()
    recent = [{"tool": str(row["tool_name"]), "args_digest": _args_digest(row["command"]),
               "outcome": str(row["outcome"])} for row in reversed(calls)]
    trust = []
    if resolved_repo:
        rows = conn.execute(
            "SELECT action_class, level, successes_at_level FROM agent_licenses "
            "WHERE repo = ? AND principal = ? ORDER BY action_class",
            (resolved_repo, principal),
        ).fetchall()
        trust = [{"class": str(row["action_class"]), "level": int(row["level"]),
                  "streak": int(row["successes_at_level"])} for row in rows]
    call = current_call or {}
    safe_call = {k: call[k] for k in ("tool", "principal") if k in call}
    if "input" in call:
        safe_call["args_digest"] = _args_digest(json.dumps(call["input"], sort_keys=True, default=str))
    digest = {
        "goal": str(turn["prompt"] if turn else "")[:4000],
        "turn": _turn_so_far(conn, turn),
        "recent_calls": recent,
        "trust": trust,
        "current_call": {**safe_call, "principal": principal},
    }
    return digest


def encode(digest: dict) -> str:
    """Encode a digest while preserving valid JSON under the hard size cap."""
    value = json.loads(json.dumps(digest, default=str))
    while True:
        text = json.dumps(value, separators=(",", ":"), ensure_ascii=True)
        if len(text) <= MAX_CHARS:
            return text
        if isinstance(value.get("recent_calls"), list) and value["recent_calls"]:
            value["recent_calls"] = value["recent_calls"][-max(1, len(value["recent_calls"]) // 2):]
            continue
        if isinstance(value.get("trust"), list) and value["trust"]:
            value["trust"] = value["trust"][-max(1, len(value["trust"]) // 2):]
            continue
        goal = str(value.get("goal", ""))
        if len(goal) > 256:
            value["goal"] = goal[:len(goal) // 2]
            continue
        value["goal"] = goal[:64]
        value["turn"] = {"files_touched": [], "diff_stat": "", "failures": []}
        value["current_call"] = {"principal": value.get("current_call", {}).get("principal", "main")}
        # The reductions above are the final fallback.  Rebuild a fixed-size
        # minimal shape so a future schema addition cannot reintroduce an
        # oversized or invalid result at this terminal path.
        minimal = {
            "goal": str(value.get("goal", ""))[:64],
            "turn": {"files_touched": [], "diff_stat": "", "failures": []},
            "recent_calls": [],
            "trust": [],
            "current_call": {"principal": value.get("current_call", {}).get("principal", "main")},
        }
        return json.dumps(minimal, separators=(",", ":"), ensure_ascii=True)


def state(conn: sqlite3.Connection, session_id: str, *, repo: str = "", principal: str = "main",
          current_call: dict[str, Any] | None = None) -> str:
    return encode(build(conn, session_id, repo=repo, principal=principal, current_call=current_call))
