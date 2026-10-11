"""neatlogs depth: GenAI semantic attributes, cost per ticket, detections as
events, policy/permit ids on tool spans, and a trace link on every ticket."""

from __future__ import annotations

import json
from dataclasses import replace

from sololicense.agent import intake as intake_module
from sololicense.agent.loop import TicketAgent
from sololicense.db.repositories import settings as settings_repo
from sololicense.observability.neatlogs_client import NeatlogsClient
from sololicense.services import economics


class _FakeSpan:
    def __init__(self, name):
        self.name, self.attributes, self.events = name, {}, []

    def set_attribute(self, key, value):
        self.attributes[key] = value

    def add_event(self, name, attributes=None):
        self.events.append((name, dict(attributes or {})))

    def set_status(self, status):
        self.status = status


class _FakeSDK:
    def __init__(self):
        self.spans = []

    def trace(self, name, kind=None):
        sdk = self

        class _Ctx:
            def __enter__(self):
                span = _FakeSpan(name)
                sdk.spans.append(span)
                return span

            def __exit__(self, *exc):
                return False

        return _Ctx()


def _spans(harness, trace_id):
    rows = harness.conn.execute(
        "SELECT name, attributes FROM spans WHERE trace_id = ? ORDER BY id", (trace_id,)
    ).fetchall()
    return [(r["name"], json.loads(r["attributes"])) for r in rows]


def _span(harness, trace_id, name):
    return next(a for n, a in _spans(harness, trace_id) if n == name)


def test_gen_ai_attributes_export_unprefixed_and_detections_become_events():
    sdk = _FakeSDK()
    client = NeatlogsClient(enabled=True, project="p", _sdk=sdk)

    client.record_span(object(), "llm.chat", "ok", {
        "gen_ai.operation.name": "chat", "gen_ai.request.model": "m", "gen_ai.usage.input_tokens": 12,
    })
    client.record_span(object(), "detection.state_mismatch", "error",
                       {"severity": "critical", "message": "nothing moved"})

    llm, detection = sdk.spans
    assert llm.attributes["gen_ai.operation.name"] == "chat"
    assert llm.attributes["gen_ai.usage.input_tokens"] == 12
    assert "sololicense.gen_ai.request.model" not in llm.attributes
    assert detection.events == [("detection", {
        "detection.rule": "state_mismatch", "detection.severity": "critical",
        "detection.message": "nothing moved",
    })]


def test_llm_intake_records_a_gen_ai_span_with_model_and_usage(harness, monkeypatch):
    answer = json.dumps({"action": "refund", "order_id": "ORD-1001", "amount": None,
                         "reason": "broken", "confidence": 0.9, "needs_human": False})
    monkeypatch.setattr(intake_module, "complete_with_usage",
                        lambda config, prompt, max_tokens=300: (answer, {"input_tokens": 120, "output_tokens": 30}))
    config = replace(harness.config, llm_provider="anthropic", anthropic_api_key="test-key")
    agent = TicketAgent(harness.conn, config, tracer=harness.agent._tracer, worker=harness.worker)

    out = agent.handle("ORD-1001 arrived broken, refund please", sender="ada@example.com")

    llm = _span(harness, out.trace_id, "llm.chat")
    assert llm["gen_ai.operation.name"] == "chat"
    assert llm["gen_ai.provider.name"] == "anthropic"
    assert llm["gen_ai.request.model"] == config.llm_model
    assert llm["gen_ai.usage.input_tokens"] == 120
    assert llm["gen_ai.usage.output_tokens"] == 30


def test_deterministic_intake_records_no_llm_span(harness):
    out = harness.agent.handle("ORD-1001 arrived broken, refund please", sender="ada@example.com")
    assert "llm.chat" not in [n for n, _ in _spans(harness, out.trace_id)]


def test_ticket_done_span_carries_the_cost_of_the_ticket(harness):
    out = harness.agent.handle("ORD-1001 arrived broken, refund please", sender="ada@example.com")

    done = _span(harness, out.trace_id, "ticket.done")
    assumptions = economics.Assumptions.from_settings(settings_repo.get_all(harness.conn))
    level = int(out.run.transition.old.effective_level)
    assert done["cost.level"] == level
    assert done["cost.usd"] == round(economics.cost_per_action(level, assumptions), 4)


def test_ticket_sent_to_a_person_costs_a_full_human_handling(harness):
    out = harness.agent.handle("Refund ORD-1001", sender="mallory@example.net")

    done = _span(harness, out.trace_id, "ticket.done")
    assumptions = economics.Assumptions.from_settings(settings_repo.get_all(harness.conn))
    assert done["cost.level"] == 0
    assert done["cost.usd"] == round(economics.cost_per_action(0, assumptions), 4)


def test_tool_execute_span_names_the_policy_version_and_permit(harness):
    out = harness.agent.handle("ORD-1001 arrived broken, refund please", sender="ada@example.com")

    execute = _span(harness, out.trace_id, "tool.execute_refund")
    permit_ids = [r["id"] for r in harness.conn.execute("SELECT id FROM execution_permits")]
    assert execute["policy.version"] == 1
    assert execute["permit.id"] in permit_ids
