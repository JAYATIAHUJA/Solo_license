"""Every coding decision is a neatlogs span; lost trust is a neatlogs incident;
every license event links to its trace and to the agent's Entire checkpoint."""

from __future__ import annotations

import json
import subprocess
from dataclasses import replace

import pytest

from sololicense.coding.gate import CodingGate
from sololicense.coding.jev import JevClient
from sololicense.db.repositories import agent as agent_repo
from sololicense.observability.neatlogs_client import NeatlogsClient
from sololicense.observability.tracer import Tracer
from sololicense.services.git_ledger import GitLedger

CHECKPOINT = "a3b2c4d5e6f7"


class _FakeSpan:
    def __init__(self, name):
        self.name, self.attributes, self.events, self.status = name, {}, [], None

    def set_attribute(self, key, value):
        self.attributes[key] = value

    def add_event(self, name, attributes=None):
        self.events.append((name, dict(attributes or {})))

    def set_status(self, status):
        self.status = status


class _FakeSDK:
    def __init__(self):
        self.spans, self.trace_kwargs = [], []

    def trace(self, name, kind=None, **kwargs):
        sdk = self
        sdk.trace_kwargs.append((name, kwargs))

        class _Ctx:
            def __enter__(self):
                span = _FakeSpan(name)
                sdk.spans.append(span)
                return span

            def __exit__(self, *exc):
                return False

        return _Ctx()

    def incidents(self):
        return [s.name for s in self.spans if s.status is not None]


def _git_init(path):
    path.mkdir()
    for args in (["init", "-q"], ["config", "user.name", "Test"], ["config", "user.email", "t@example.com"]):
        subprocess.run(["git", *args], cwd=path, check=True)
    (path / "app.py").write_text("print('hi')\n")
    subprocess.run(["git", "add", "."], cwd=path, check=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=path, check=True)
    return path


@pytest.fixture
def sdk():
    return _FakeSDK()


@pytest.fixture
def gate(harness, tmp_path, sdk):
    project = _git_init(tmp_path / "shop-api")
    tracer = Tracer(NeatlogsClient(enabled=True, project="p", _sdk=sdk))
    gate = CodingGate(harness.conn, tracer, GitLedger(repo_root=harness.repo), jev_client=JevClient(),
                      checkpoint_lookup=lambda cwd, session: {"checkpoint_id": CHECKPOINT + "9999"})
    gate.project = project
    return gate


def _event(gate, **fields):
    return {"session_id": "s1", "cwd": str(gate.project), **fields}


def _bash(gate, command):
    return _event(gate, tool_name="Bash", tool_input={"command": command})


def _turn(gate):
    return agent_repo.current_turn(gate.conn, "s1")


def _spans(gate, name):
    trace = gate._traces[_turn(gate)["id"]]
    return [s for s in trace.spans if s.name == name]


def _stored(gate, trace_id, name):
    rows = gate.conn.execute("SELECT name, attributes FROM spans WHERE trace_id = ? ORDER BY id", (trace_id,))
    return [json.loads(r["attributes"]) for r in rows if r["name"] == name]


def _last_event(gate):
    return gate.conn.execute("SELECT * FROM agent_events ORDER BY id DESC LIMIT 1").fetchone()


def _failed_install(gate):
    gate.user_prompt(_event(gate, prompt="add left-pad"))
    agent_repo.get_license(gate.conn, "shop-api", "install-dep")
    agent_repo.set_level(gate.conn, "shop-api", "install-dep", 2)
    agent_repo.approve_pattern(gate.conn, "shop-api", "install-dep", "npm install")
    gate.permission(_bash(gate, "npm install left-pad"))
    return gate.tool_result(_bash(gate, "npm install left-pad") | {"error": "Exit code 1\nE404"}, failed=True)


def test_a_demotion_is_an_incident_span_linked_to_the_turn_trace_and_checkpoint(gate, sdk):
    answer = _failed_install(gate)
    turn = _turn(gate)

    event = _last_event(gate)
    assert (event["kind"], event["from_level"], event["to_level"]) == ("demote", 2, 0)
    assert event["trace_id"] == turn["trace_id"]
    assert event["entire_checkpoint"] == CHECKPOINT + "9999"
    assert agent_repo.get_turn(gate.conn, turn["id"])["entire_checkpoint"] == CHECKPOINT + "9999"

    demote = _spans(gate, "license.demote")[0].attributes
    assert {k: demote[k] for k in ("repo", "action_class", "principal", "agent", "from_level", "to_level")} == {
        "repo": "shop-api", "action_class": "install-dep", "principal": "main", "agent": "claude-code",
        "from_level": 2, "to_level": 0}
    assert "npm install left-pad failed" in demote["reason"]
    assert demote["entire_checkpoint"] == CHECKPOINT + "9999" and demote["incident"] is True

    sent = _spans(gate, "remediation.sent")[0].attributes
    assert {k: sent[k] for k in ("repo", "action_class", "principal", "agent", "from_level", "to_level")} == {
        "repo": "shop-api", "action_class": "install-dep", "principal": "main", "agent": "claude-code",
        "from_level": 2, "to_level": 0}
    assert sent["reason"].startswith("npm install left-pad failed")
    assert "incident" not in sent

    assert sdk.incidents() == ["license.demote"]
    marked = next(s for s in sdk.spans if s.name == "license.demote")
    assert ("incident", {"incident.kind": "demote", "incident.reason": demote["reason"][:200]}) in marked.events

    context = answer["hookSpecificOutput"]["additionalContext"]
    assert f"entire checkpoint explain {CHECKPOINT}" in context
    assert context.startswith("Solo License: `npm install left-pad` failed and install-dep is back to asking.")

    message = subprocess.run(["git", "log", "-1", "--format=%B", event["git_sha"]], cwd=gate.ledger._repo_root,
                             capture_output=True, text=True, check=True).stdout
    assert f"trace: {turn['trace_id']}" in message
    assert f"agent checkpoint: entire checkpoint explain {CHECKPOINT}" in message


def test_a_failure_that_demotes_nothing_looks_up_no_checkpoint(gate, sdk):
    calls = []
    gate.checkpoint_lookup = lambda cwd, session: calls.append(session) or {"checkpoint_id": CHECKPOINT}
    gate.user_prompt(_event(gate, prompt="add left-pad"))
    gate.permission(_bash(gate, "npm install left-pad"))
    answer = gate.tool_result(_bash(gate, "npm install left-pad") | {"error": "E404"}, failed=True)

    assert calls == []
    assert "entire checkpoint explain" not in answer["hookSpecificOutput"]["additionalContext"]
    assert sdk.incidents() == []


def test_turn_spans_carry_who_and_where_and_the_session_groups_them_in_neatlogs(gate, sdk):
    gate.user_prompt(_event(gate, prompt="x", _agent="codex"))
    start = _spans(gate, "turn.start")[0].attributes
    assert (start["repo"], start["agent"], start["principal"]) == ("shop-api", "codex", "main")
    assert ("coding.turn.run", {"session_id": "s1"}) in sdk.trace_kwargs


def test_flagging_writes_an_incident_and_links_the_event_to_its_trace_and_checkpoint(gate, sdk):
    gate.checkpoint_lookup = lambda cwd, session: None
    gate.user_prompt(_event(gate, prompt="add left-pad"))
    agent_repo.get_license(gate.conn, "shop-api", "install-dep")
    agent_repo.set_level(gate.conn, "shop-api", "install-dep", 2)
    agent_repo.approve_pattern(gate.conn, "shop-api", "install-dep", "npm install")
    gate.permission(_bash(gate, "npm install left-pad"))
    gate.tool_result(_bash(gate, "npm install left-pad"), failed=False)
    turn = _turn(gate)
    agent_repo.set_checkpoint(gate.conn, turn["id"], CHECKPOINT)
    decision = gate.conn.execute("SELECT id FROM agent_decisions ORDER BY id DESC LIMIT 1").fetchone()["id"]
    sdk.spans.clear()

    result = gate.flag(decision_id=decision, actor_id="human:jayati", reason="not this package")

    event = _last_event(gate)
    assert event["kind"] == "flag" and event["entire_checkpoint"] == CHECKPOINT
    assert event["trace_id"] and event["trace_id"] != turn["trace_id"]
    flagged = _stored(gate, event["trace_id"], "turn.flagged")[0]
    assert {k: flagged[k] for k in ("repo", "action_class", "principal", "agent", "reason")} == {
        "repo": "shop-api", "action_class": "install-dep", "principal": "main", "agent": "claude-code",
        "reason": "not this package"}
    assert flagged["turn_trace_id"] == turn["trace_id"] and flagged["entire_checkpoint"] == CHECKPOINT
    change = _stored(gate, event["trace_id"], "license.flag")[0]
    assert (change["from_level"], change["to_level"], change["incident"]) == (2, 0, True)
    queued = _stored(gate, event["trace_id"], "remediation.queued")[0]
    assert queued["kind"] == "flagged" and queued["repo"] == "shop-api"
    assert "incident" not in queued
    assert sorted(sdk.incidents()) == ["license.flag", "turn.flagged"]
    assert f"entire checkpoint explain {CHECKPOINT}" in result["text"]


def test_a_policy_change_event_has_its_own_trace(gate):
    gate.record_policy("shop-api", "deny: rm -rf", "human:jayati")
    event = _last_event(gate)
    assert event["kind"] == "policy" and event["trace_id"]
    assert event["entire_checkpoint"] is None
    policy = _stored(gate, event["trace_id"], "license.policy")[0]
    assert (policy["repo"], policy["action_class"], policy["principal"]) == ("shop-api", "policy", "main")
    assert policy["git_sha"] == event["git_sha"]


def test_the_third_denial_interrupt_is_an_incident(gate, sdk):
    gate.user_prompt(_event(gate, prompt="ship"))
    for _ in range(3):
        gate.permission(_bash(gate, "git push --force origin main"))

    sent = _spans(gate, "remediation.sent")
    assert len(sent) == 1
    attrs = sent[0].attributes
    assert attrs["interrupt"] is True and attrs["incident"] is True and attrs["kind"] == "denied"
    assert (attrs["repo"], attrs["agent"], attrs["principal"]) == ("shop-api", "claude-code", "main")
    assert attrs["action_class"] and attrs["reason"]
    assert "remediation.sent" in sdk.incidents()


def test_a_loop_stop_is_an_incident_and_guidance_is_not(gate, sdk):
    gate.user_prompt(_event(gate, prompt="get the build green"))
    for _ in range(4):
        gate.permission(_bash(gate, "pip install -e ."))
        gate.tool_result(_bash(gate, "pip install -e .") | {"error": "Exit code 1\nERROR: no setup.py"}, failed=True)
    guidance = _spans(gate, "detection.loop")
    assert guidance and all(not s.attributes.get("incident") for s in guidance)
    assert guidance[-1].attributes["repo"] == "shop-api"
    assert guidance[-1].attributes["action_class"] == "install-dep"

    gate.permission(_bash(gate, "pip install -e ."))
    stop = _spans(gate, "detection.loop")[-1].attributes
    assert stop["severity"] == "critical" and stop["interrupt"] is True and stop["incident"] is True
    assert (stop["repo"], stop["action_class"], stop["principal"], stop["agent"]) == \
        ("shop-api", "install-dep", "main", "claude-code")
    assert sdk.incidents().count("detection.loop") == 1


def test_a_forbidden_action_refused_at_pre_tool_use_is_an_incident(gate, sdk):
    gate.user_prompt(_event(gate, prompt="ship"))
    gate.pre_tool(_bash(gate, "git push --force origin main"))
    denied = _spans(gate, "gate.deny")[-1].attributes
    assert denied["hook"] == "PreToolUse" and denied["decided_by"] == "hard-deny"
    forbidden = _spans(gate, "detection.forbidden_action")[-1].attributes
    assert forbidden["severity"] == "critical" and forbidden["incident"] is True
    assert forbidden["hook"] == "PreToolUse"
    assert sdk.incidents().count("detection.forbidden_action") == 1


def test_a_loop_halt_refused_at_pre_tool_use_is_an_incident(gate, sdk):
    gate.user_prompt(_event(gate, prompt="x"))
    for _ in range(4):
        gate.tool_result(_bash(gate, "cat app.py"), failed=False)
    gate.pre_tool(_bash(gate, "cat app.py"))
    stop = _spans(gate, "detection.loop")[-1].attributes
    assert stop["kind"] == "loop-stop" and stop["interrupt"] is True and stop["incident"] is True
    assert stop["hook"] == "PreToolUse"


def test_a_loop_stopped_after_the_run_is_an_incident_too(gate, sdk):
    gate.user_prompt(_event(gate, prompt="read it again", _agent="cursor"))
    for _ in range(5):  # never asked the gate: the agent's settings let it run
        answer = gate.tool_result(_bash(gate, "cat app.py"), failed=False)

    assert answer["continue"] is False
    stop = _spans(gate, "detection.loop")[-1].attributes
    assert stop["kind"] == "loop-stop" and stop["interrupt"] is True and stop["incident"] is True
    assert (stop["repo"], stop["agent"]) == ("shop-api", "cursor")
    assert sdk.incidents().count("detection.loop") == 1


def test_a_failed_turn_links_its_demotions_to_the_checkpoint(gate, sdk):
    gate.verifier = lambda g, turn, decisions: (False, "tests fail after the change.", {"tests": "failed"})
    gate.user_prompt(_event(gate, prompt="fix"))
    agent_repo.get_license(gate.conn, "shop-api", "git-local")
    agent_repo.set_level(gate.conn, "shop-api", "git-local", 1)
    gate.permission(_bash(gate, "git commit -m x"))
    gate.tool_result(_bash(gate, "git commit -m x"), failed=False)

    answer = gate.stop(_event(gate))

    event = _last_event(gate)
    assert event["kind"] == "demote" and event["entire_checkpoint"] == CHECKPOINT + "9999"
    blocked = _spans(gate, "remediation.sent")[-1].attributes
    assert blocked["kind"] == "turn-failed" and blocked["entire_checkpoint"] == CHECKPOINT + "9999"
    assert blocked["repo"] == "shop-api" and blocked["reason"] == "tests fail after the change."
    assert f"entire checkpoint explain {CHECKPOINT}" in answer["reason"]


def test_old_databases_gain_the_event_link_columns(tmp_path):
    import sqlite3

    from sololicense.db.database import apply_schema

    conn = sqlite3.connect(tmp_path / "old.db")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE agent_events (id INTEGER PRIMARY KEY AUTOINCREMENT, repo TEXT NOT NULL, "
        "principal TEXT NOT NULL DEFAULT 'main', action_class TEXT NOT NULL, kind TEXT NOT NULL, "
        "from_level INTEGER NOT NULL, to_level INTEGER NOT NULL, reason TEXT NOT NULL, actor_id TEXT NOT NULL, "
        "git_sha TEXT, created_at TEXT NOT NULL DEFAULT (datetime('now')))")
    conn.execute("INSERT INTO agent_events (repo, action_class, kind, from_level, to_level, reason, actor_id) "
                 "VALUES ('r', 'git-local', 'demote', 1, 0, 'x', 'system')")
    apply_schema(conn)
    apply_schema(conn)
    columns = {r["name"] for r in conn.execute("PRAGMA table_info(agent_events)")}
    assert {"trace_id", "entire_checkpoint"} <= columns
    row = conn.execute("SELECT trace_id, entire_checkpoint FROM agent_events").fetchone()
    assert tuple(row) == (None, None)


def test_the_coding_payload_links_each_event_to_neatlogs(gate, harness, tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from sololicense.api import app as app_module
    from sololicense.db.database import init_db

    conn = init_db(tmp_path / "links.db", check_same_thread=False)
    threaded = CodingGate(conn, gate.tracer, GitLedger(repo_root=harness.repo), jev_client=JevClient(),
                          checkpoint_lookup=lambda cwd, session: {"checkpoint_id": CHECKPOINT})

    class Ctx:
        coding_gate = threaded
        config = replace(harness.config, neatlogs_api_key="k", neatlogs_app_url="https://app.neatlogs.com")

    Ctx.conn = conn
    monkeypatch.setattr(app_module, "get_context", lambda: Ctx)
    client = TestClient(app_module.app)
    client.post("/api/hooks/user-prompt", json=_event(gate, prompt="add left-pad"))
    agent_repo.get_license(conn, "shop-api", "install-dep")
    agent_repo.set_level(conn, "shop-api", "install-dep", 2)
    conn.commit()
    client.post("/api/hooks/permission", json=_bash(gate, "npm install left-pad"))
    client.post("/api/hooks/post-tool-failure", json=_bash(gate, "npm install left-pad") | {"error": "E404"})

    event = client.get("/api/coding").json()["events"][0]
    assert event["kind"] == "demote" and event["entire_checkpoint"] == CHECKPOINT
    assert event["neatlogs_link"] == f"https://app.neatlogs.com/traces/{event['trace_id']}"
