import json
import sys
from dataclasses import replace
from types import SimpleNamespace

from sololicense.agent.intake import complete, parse_llm_response


def test_parse_llm_response_accepts_valid_schema():
    parsed = parse_llm_response(
        json.dumps(
            {
                "order_id": "ord-1001",
                "amount": 25,
                "reason": "defective item",
                "confidence": 0.92,
                "needs_human": False,
            }
        ),
        model="claude-haiku-5-5",
    )

    assert parsed is not None
    assert parsed.order_id == "ORD-1001"
    assert parsed.amount == 25.0
    assert parsed.reason == "defective item"
    assert parsed.confidence == 0.92
    assert parsed.needs_human is False
    assert parsed.source == "llm:claude-haiku-5-5"


def test_parse_llm_response_rejects_free_text_wrapped_json():
    parsed = parse_llm_response(
        'Sure: {"order_id": "ORD-1001", "amount": 25, "reason": "x"}',
        model="claude-haiku-5-5",
    )

    assert parsed is None


def test_parse_llm_response_rejects_invalid_confidence():
    parsed = parse_llm_response(
        json.dumps(
            {
                "order_id": "ORD-1001",
                "amount": 25,
                "reason": "x",
                "confidence": 2,
            }
        ),
        model="claude-haiku-5-5",
    )

    assert parsed is None


def test_anthropic_completion_uses_configured_timeout_and_retries(monkeypatch, harness):
    calls = []

    class FakeClient:
        def __init__(self, **kwargs):
            calls.append(kwargs)
            self.messages = SimpleNamespace(
                create=lambda **_: SimpleNamespace(
                    content=[SimpleNamespace(type="text", text="ready")]
                )
            )

    monkeypatch.setitem(sys.modules, "anthropic", SimpleNamespace(Anthropic=FakeClient))
    config = replace(
        harness.config,
        llm_provider="anthropic",
        anthropic_api_key="test-key",
        llm_timeout_seconds=12.5,
        llm_max_retries=3,
    )

    assert complete(config, "status?", max_tokens=10) == "ready"
    assert calls == [{"api_key": "test-key", "timeout": 12.5, "max_retries": 3}]
