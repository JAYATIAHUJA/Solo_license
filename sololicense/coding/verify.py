"""End-of-turn checks: did the turn's changes work, and were they what was asked?

Run once per turn from the ``Stop`` hook, never per edit:

1. **Scope.** The diff since the prompt is compared with the request. A
   one-line bug fix that rewrites fifty lines in four files is over-editing:
   the turn is sent back with the files that look unrelated. Jev grades the
   diff when a key is configured; otherwise a size-and-spread rule does.
2. **Tests.** If the repository has a test command (configured, or found in
   ``package.json`` / pytest config), it runs. Failing tests after a turn
   that changed code are evidence against the classes that changed it.

The result decides whether the turn's changes count as verified evidence.
"""

from __future__ import annotations

import json
import re
import sqlite3
import subprocess
from dataclasses import dataclass
from pathlib import Path

from sololicense.coding import jev
from sololicense.db.repositories import agent as agent_repo

TEST_TIMEOUT_SECONDS = 120
_SMALL_REQUEST = re.compile(r"\b(fix|bug|typo|rename|small|tiny|one[- ]line|quick|minor|off[- ]by[- ]one|tweak)\b", re.I)
_TEST_FILE = re.compile(r"(^|/)(tests?/|test_|.*\.(test|spec)\.)")


@dataclass(frozen=True)
class FileChange:
    path: str
    lines: int


def _run(cwd: str, args: list[str], timeout: float = 15.0) -> subprocess.CompletedProcess | None:
    try:
        return subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None


def changed_files(cwd: str, base: str | None) -> list[FileChange]:
    """Files changed since ``base`` (tracked) plus new untracked files."""
    changes: list[FileChange] = []
    numstat = _run(cwd, ["git", "diff", "--numstat", base or "HEAD"])
    for line in (numstat.stdout if numstat and numstat.returncode == 0 else "").splitlines():
        added, deleted, path = (line.split("\t", 2) + ["", ""])[:3]
        lines = (int(added) if added.isdigit() else 0) + (int(deleted) if deleted.isdigit() else 0)
        changes.append(FileChange(path, lines))
    untracked = _run(cwd, ["git", "ls-files", "--others", "--exclude-standard"])
    for path in (untracked.stdout if untracked and untracked.returncode == 0 else "").splitlines():
        try:
            lines = sum(1 for _ in (Path(cwd) / path).open(encoding="utf-8", errors="ignore"))
        except OSError:
            lines = 0
        changes.append(FileChange(path, lines))
    return [c for c in changes if c.path and not c.path.startswith("ledger/")]


def diff_text(cwd: str, base: str | None, limit: int = 12000) -> str:
    result = _run(cwd, ["git", "diff", "--unified=2", base or "HEAD"])
    return (result.stdout if result and result.returncode == 0 else "")[:limit]


def _mentioned(path: str, request: str) -> bool:
    text = request.lower()
    name = Path(path).name.lower()
    stem = Path(path).stem.lower().removeprefix("test_").split(".")[0]
    return name in text or (len(stem) >= 3 and re.search(rf"\b{re.escape(stem)}\b", text) is not None)


def scope_by_rule(request: str, changes: list[FileChange]) -> dict:
    """Grade 1..5 how proportionate a diff is, from its size and spread."""
    lines = sum(c.lines for c in changes)
    mentioned = sum(1 for c in changes if _mentioned(c.path, request))
    small = bool(_SMALL_REQUEST.search(request)) and len(request) < 400
    line_budget = 40 if small else 200
    file_budget = max(2, mentioned + 1) if small else max(5, mentioned + 3)
    if lines <= line_budget and len(changes) <= file_budget:
        score = 5
    elif lines <= 1.5 * line_budget and len(changes) <= file_budget + 1:
        score = 4
    elif lines <= 2.5 * line_budget:
        score = 3
    elif lines <= 5 * line_budget:
        score = 2
    else:
        score = 1
    if len(changes) > file_budget + 3:
        score = min(score, 2)
    return {"score": score, "confidence": 1.0, "source": "rules", "small_request": small}


def drift(request: str, changes: list[FileChange]) -> list[FileChange]:
    """Changed files the request never points at, biggest first. Tests that
    belong to a mentioned file are not drift."""
    mentioned_stems = {Path(c.path).stem.lower().removeprefix("test_").split(".")[0]
                       for c in changes if _mentioned(c.path, request)}
    out = []
    for c in changes:
        stem = Path(c.path).stem.lower().removeprefix("test_").split(".")[0]
        if _mentioned(c.path, request) or (_TEST_FILE.search(c.path) and stem in mentioned_stems):
            continue
        out.append(c)
    return sorted(out, key=lambda c: -c.lines)


def detect_test_command(root: str) -> str | None:
    package = Path(root) / "package.json"
    if package.exists():
        try:
            script = json.loads(package.read_text(encoding="utf-8")).get("scripts", {}).get("test", "")
        except (OSError, ValueError):
            script = ""
        if script and "no test specified" not in script:
            return "npm test --silent"
    pyproject = Path(root) / "pyproject.toml"
    if (Path(root) / "pytest.ini").exists() or (
            pyproject.exists() and "[tool.pytest" in pyproject.read_text(encoding="utf-8", errors="ignore")):
        return "python -m pytest -q -x"
    return None


def run_tests(root: str, command: str) -> tuple[bool, str]:
    try:
        result = subprocess.run(command, cwd=root, shell=True, capture_output=True, text=True,
                                timeout=TEST_TIMEOUT_SECONDS, check=False)
    except subprocess.TimeoutExpired:
        return False, f"timed out after {TEST_TIMEOUT_SECONDS}s"
    except OSError as error:
        return False, str(error)
    tail = "\n".join((result.stdout + result.stderr).strip().splitlines()[-6:])
    return result.returncode == 0, tail


def check_turn(gate, turn: sqlite3.Row, decisions: list[sqlite3.Row]) -> tuple[bool, str, dict]:
    """The verifier the gate calls at ``Stop``: (ok, reason, details)."""
    root, request = turn["cwd"], turn["prompt"] or ""
    changes = changed_files(root, turn["base_ref"])
    lines = sum(c.lines for c in changes)
    details: dict = {"lines_changed": lines, "files_changed": len(changes), "tests": "none"}
    if not changes:
        return True, "", details

    # 1. Scope, only when we know what was asked.
    if request.strip():
        grade = None
        if gate.jev_client.enabled:
            grade = jev.score_diff(gate.jev_client, request, diff_text(root, turn["base_ref"]))
            if grade and grade["confidence"] < jev.MIN_CHOICE_CONFIDENCE:
                grade = None
        grade = grade or scope_by_rule(request, changes)
        details.update(scope_score=grade["score"], scope_source=grade["source"])
        if grade["score"] <= 2:
            unrelated = drift(request, changes)[:5]
            listed = ", ".join(f"{c.path} ({c.lines} lines)" for c in unrelated) or "the extra changes"
            details["blame"] = ["file-edit"]
            return False, (
                f"over-editing: this turn changed {lines} lines in {len(changes)} files for this request "
                f"(scope {grade['score']}/5). Keep only the change that was asked for and revert the "
                f"unrelated edits in: {listed}."
            ), details

    # 2. Tests.
    repo = agent_repo.ensure_repo(gate.conn, turn["repo"], root)
    command = repo["test_command"] or detect_test_command(root)
    if command:
        passed, tail = run_tests(root, command)
        details["tests"] = "passed" if passed else "failed"
        details["test_command"] = command
        if not passed:
            details["blame"] = ["file-edit"]
            return False, f"the tests fail after this turn's changes (`{command}`):\n{tail}\nFix them before finishing.", details
    return True, "", details
