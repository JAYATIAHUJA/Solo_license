"""Entire: the agent's session history behind every license change.

Entire records each Claude Code session as checkpoints linked to commits, and
its session id *is* Claude Code's ``session_id``, the same one our hooks
receive. So when a turn fails, the evidence can point at the exact Entire
session and the last checkpoint before the failure (``entire checkpoint
explain <id>`` shows the prompts, tool calls and files behind it), and a
person can put the working tree back to how it was before the turn.

Entire is optional: without the CLI every function here returns nothing.
"""

from __future__ import annotations

import json
import shutil
import subprocess


def _entire(cwd: str, *args: str, timeout: float = 15.0) -> object | None:
    if shutil.which("entire") is None:
        return None
    try:
        result = subprocess.run(["entire", *args, "--json"], cwd=cwd, capture_output=True, text=True,
                                timeout=timeout, check=False, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    try:
        return json.loads(result.stdout)
    except ValueError:
        return None


def last_checkpoint(cwd: str, session_id: str) -> dict | None:
    """The most recent Entire checkpoint of this session on the current branch."""
    rows = _entire(cwd, "checkpoint", "list")
    if not isinstance(rows, list):
        return None
    mine = [r for r in rows if isinstance(r, dict) and r.get("session_id") == session_id]
    if not mine:
        return None
    best = max(mine, key=lambda r: str(r.get("date", "")))
    return {"checkpoint_id": str(best.get("checkpoint_id", "")), "date": best.get("date"),
            "message": str(best.get("message", ""))[:120]}


def explain_command(checkpoint_id: str) -> str:
    return f"entire checkpoint explain {checkpoint_id[:12]}"


def rewind(cwd: str, base_ref: str | None, label: str) -> dict:
    """Put the working tree back to the snapshot taken at the turn's prompt.

    Nothing is thrown away: the turn's changes are stashed first (``git stash
    list`` shows them under ``label``), then the pre-turn snapshot is applied
    if the tree was not clean when the turn started."""
    def git(*args):
        return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=30, check=False)

    head = git("rev-parse", "HEAD").stdout.strip()
    saved = git("stash", "push", "--include-untracked", "-m", label)
    if saved.returncode != 0:
        return {"ok": False, "error": (saved.stderr or saved.stdout).strip()[:300]}
    if base_ref and base_ref != head:
        applied = git("stash", "apply", base_ref)
        if applied.returncode != 0:
            return {"ok": False, "error": (applied.stderr or applied.stdout).strip()[:300], "stashed": label}
    return {"ok": True, "stashed": label, "restored_to": base_ref or head}
