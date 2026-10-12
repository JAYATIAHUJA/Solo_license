"""neatlogs depth: GenAI semantic attributes export unprefixed and detections
become span events."""

from __future__ import annotations

from sololicense.observability.neatlogs_client import NeatlogsClient


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
