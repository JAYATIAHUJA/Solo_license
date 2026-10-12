from __future__ import annotations

import json

from sololicense.coding import digest
from sololicense.db.repositories import agent as agent_repo


def test_digest_keeps_goal_and_principal_scoped_recent_calls(harness):
    agent_repo.open_turn(harness.conn, session_id="s", repo="repo", cwd=".", prompt="ship the parser",
                         base_ref=None, trace_id=None, principal="subagent:Explore")
    turn_id = agent_repo.current_turn(harness.conn, "s", principal="subagent:Explore")["id"]
    agent_repo.insert_decision(harness.conn, session_id="s", agent="cursor", principal="subagent:Explore",
                               turn_id=turn_id, repo="repo", tool_name="Bash", action_class="test-run",
                               pattern="pytest", command="pytest -q", decision="allow", decided_by="license",
                               level=2, source="rules", outcome="verified", reason="", trace_id=None)

    value = json.loads(digest.state(harness.conn, "s", repo="repo", principal="subagent:Explore",
                                    current_call={"tool": "Bash"}))

    assert value["goal"] == "ship the parser"
    assert value["recent_calls"][0]["tool"] == "Bash"
    assert value["current_call"]["principal"] == "subagent:Explore"


def test_digest_is_bounded(harness):
    agent_repo.open_turn(harness.conn, session_id="large", repo="repo", cwd=".", prompt="x" * 100_000,
                         base_ref=None, trace_id=None)
    assert len(digest.state(harness.conn, "large")) <= digest.MAX_CHARS


def test_bounded_encoding_remains_valid_json():
    encoded = digest.encode({"goal": "x" * 100_000, "recent_calls": [], "trust": [],
                             "turn": {}, "current_call": {"principal": "main"}})
    assert len(encoded) <= digest.MAX_CHARS
    assert json.loads(encoded)["current_call"]["principal"] == "main"


def test_session_rows_allow_one_digest_per_principal(harness):
    harness.conn.execute("INSERT INTO agent_sessions(session_id, agent, repo, principal, digest) VALUES(?,?,?,?,?)",
                         ("shared", "claude-code", "repo", "main", "{}"))
    harness.conn.execute("INSERT INTO agent_sessions(session_id, agent, repo, principal, digest) VALUES(?,?,?,?,?)",
                         ("shared", "claude-code", "repo", "subagent:Explore", "{}"))
    assert harness.conn.execute("SELECT COUNT(*) FROM agent_sessions WHERE session_id='shared'").fetchone()[0] == 2
