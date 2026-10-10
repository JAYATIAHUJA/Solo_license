import json

from sololicense.agent.intake import parse_llm_response


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
