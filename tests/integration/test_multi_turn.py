"""A conversation across two messages: the agent asks, the customer answers.

A reply never re-handles the earlier ticket (that path returns 409 so a
double-submit cannot demote the licence). It arrives as a new ticket linked
to the open question by ``follows_ticket_id``.
"""

from __future__ import annotations

from dataclasses import replace

from fastapi.testclient import TestClient

from sololicense.api import app as api_module
from sololicense.bootstrap import build_app


def _client(monkeypatch, harness) -> TestClient:
    monkeypatch.delenv("SOLO_API_TOKENS", raising=False)
    context = build_app(replace(harness.config, demo_mode=True), check_same_thread=False)
    monkeypatch.setattr(api_module, "_context", context)
    monkeypatch.setattr(api_module, "_authenticator", None, raising=False)
    monkeypatch.setattr(api_module, "_demo_sessions", {})
    monkeypatch.setattr(api_module, "reset_context", lambda: None)
    # A second open order for Ada, so "refund please" is ambiguous.
    context.conn.execute(
        "INSERT INTO orders (order_id, customer, amount, refunded_amount, status, email, ordered_at, source)"
        " VALUES ('ORD-1010', 'Ada Lovelace', 20.0, 0, 'paid', 'ada@example.com', date('now', '-2 days'), 'sample')"
    )
    context.conn.commit()
    return TestClient(api_module.app, raise_server_exceptions=False)


def _headers(client) -> dict:
    token = client.post("/api/session/demo", json={"name": "Multi-turn"}).json()["token"]
    return {"Authorization": f"Bearer {token}"}


def _paste(client, headers, message: str) -> dict:
    return client.post(
        "/api/intake", headers=headers,
        json={"message": message, "sender": "ada@example.com"},
    ).json()["intake"]


def _ticket(client, headers, ticket_id: int) -> dict:
    tickets = client.get("/api/dashboard", headers=headers).json()["tickets"]
    return next(t for t in tickets if t["id"] == ticket_id)


def test_agent_asks_which_order_then_finishes_on_the_reply(monkeypatch, harness):
    client = _client(monkeypatch, harness)
    headers = _headers(client)

    asked = _paste(client, headers, "Hi, can I get my money back please?")
    assert asked["status"] == "needs_info"

    answered = _paste(client, headers, "It's ORD-1010.")

    assert answered["status"] == "done"
    assert answered["order_id"] == "ORD-1010"
    assert answered["amount"] == 20.0
    assert answered["follows_ticket_id"] == asked["ticket_id"]
    assert answered["steps"][0]["name"] == "context"

    earlier = _ticket(client, headers, asked["ticket_id"])
    assert earlier["status"] == "answered"
    reply = _ticket(client, headers, answered["ticket_id"])
    assert reply["follows_ticket_id"] == asked["ticket_id"]

    context = api_module._context
    spans = [row["name"] for row in context.conn.execute(
        "SELECT name FROM spans WHERE trace_id = ?", (answered["trace_id"],)
    )]
    assert "agent.context" in spans


def test_answered_question_is_not_reused_by_a_later_message(monkeypatch, harness):
    client = _client(monkeypatch, harness)
    headers = _headers(client)

    asked = _paste(client, headers, "Can I get my money back?")
    _paste(client, headers, "ORD-1010 please")
    later = _paste(client, headers, "Also ORD-1001 arrived broken, refund please.")

    assert later.get("follows_ticket_id") is None
    assert later["order_id"] == "ORD-1001"
    assert _ticket(client, headers, asked["ticket_id"])["status"] == "answered"


def test_re_handling_a_handled_ticket_still_returns_409(monkeypatch, harness):
    client = _client(monkeypatch, harness)
    headers = _headers(client)

    asked = _paste(client, headers, "Can I get my money back?")
    _paste(client, headers, "ORD-1010")

    for ticket_id in (asked["ticket_id"],):
        response = client.post(f"/api/tickets/{ticket_id}/handle", headers=headers)
        assert response.status_code == 409
