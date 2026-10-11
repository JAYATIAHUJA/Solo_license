"""Onboarding must be atomic and re-handling must not demote.

Regression guards from the reliability audit:

1. ``complete_onboarding`` validates everything (CSV contents, manual order
   ids) BEFORE persisting ``onboarded=1`` — a bad payload must never leave
   a half-onboarded workspace the UI would treat as set up.
2. Handling an already-handled ticket is rejected instead of re-running the
   agent, which would flag a duplicate action and demote the license.
"""

from __future__ import annotations

from dataclasses import replace

from fastapi.testclient import TestClient

from sololicense.api import app as api_module
from sololicense.bootstrap import build_app


def _client(monkeypatch, harness) -> TestClient:
    monkeypatch.delenv("SOLO_API_TOKENS", raising=False)
    context = build_app(
        replace(harness.config, demo_mode=True), check_same_thread=False
    )
    monkeypatch.setattr(api_module, "_context", context)
    monkeypatch.setattr(api_module, "_authenticator", None, raising=False)
    monkeypatch.setattr(api_module, "_demo_sessions", {})
    monkeypatch.setattr(api_module, "reset_context", lambda: None)
    return TestClient(api_module.app, raise_server_exceptions=False)


def _demo_headers(client) -> dict:
    token = client.post("/api/session/demo", json={"name": "Reliability"}).json()["token"]
    return {"Authorization": f"Bearer {token}"}


def _onboarded(client, headers) -> bool:
    return bool(client.get("/api/settings", headers=headers).json().get("onboarded"))


def test_a_bad_csv_leaves_no_onboarded_flag(monkeypatch, harness):
    client = _client(monkeypatch, harness)
    headers = _demo_headers(client)
    before = client.get("/api/dashboard", headers=headers).json()
    orders_before = {o["order_id"] for o in before["orders"]}

    bad = client.post(
        "/api/onboarding/complete", headers=headers,
        json={
            "business_name": "Acme", "starting_level": 1,
            "orders_csv": "name,amount\nnot,an,order,file",
            "load_sample_orders": False,
        },
    )

    assert bad.status_code == 422
    assert not _onboarded(client, headers)
    # Nothing was written, and a clean retry still works.
    ok = client.post(
        "/api/onboarding/complete", headers=headers,
        json={"business_name": "Acme", "starting_level": 1, "load_sample_orders": False},
    )
    assert ok.status_code == 200
    assert _onboarded(client, headers)


def test_a_bad_manual_order_id_leaves_no_onboarded_flag(monkeypatch, harness):
    client = _client(monkeypatch, harness)
    headers = _demo_headers(client)

    bad = client.post(
        "/api/onboarding/complete", headers=headers,
        json={
            "business_name": "Acme", "starting_level": 1,
            "orders": [{"order_id": "!!!", "customer": "C", "amount": 5}],
            "load_sample_orders": False,
        },
    )

    assert bad.status_code == 422
    assert not _onboarded(client, headers)


def test_onboarding_still_loads_the_sample_store_and_levels(monkeypatch, harness):
    client = _client(monkeypatch, harness)
    headers = _demo_headers(client)
    harness.conn.execute("DELETE FROM orders")
    harness.conn.commit()

    ok = client.post(
        "/api/onboarding/complete", headers=headers,
        json={
            "business_name": "Acme", "starting_levels": {"refund": 1, "store_credit": 2},
            "load_sample_orders": True,
            "orders": [{"order_id": "ORD-7777", "customer": "Manual", "amount": 12}],
        },
    )

    assert ok.status_code == 200
    body = ok.json()
    assert _onboarded(client, headers)
    ids = {o["order_id"] for o in body["orders"]}
    assert "ORD-7777" in ids and "ORD-1001" in ids
    assert body["licenses"]["refund"]["level"] == 1
    assert body["licenses"]["store_credit"]["level"] == 2


def test_rehandling_a_handled_ticket_is_rejected_without_demoting(monkeypatch, harness):
    client = _client(monkeypatch, harness)
    headers = _demo_headers(client)
    ticket_id = client.get("/api/dashboard", headers=headers).json()["tickets"][0]["id"]

    first = client.post(f"/api/tickets/{ticket_id}/handle", headers=headers)
    assert first.status_code == 200
    failures_after_first = first.json()["licenses"]["refund"]["failures"]

    second = client.post(f"/api/tickets/{ticket_id}/handle", headers=headers)

    assert second.status_code == 409
    dashboard = client.get("/api/dashboard", headers=headers).json()
    assert dashboard["licenses"]["refund"]["failures"] == failures_after_first
