from dataclasses import replace

from fastapi.testclient import TestClient

from app import api as api_module
from sololicense.bootstrap import build_app


def test_provider_catalogue_includes_groq_and_zcode_with_no_manual_url():
    providers = {provider["key"]: provider for provider in api_module.serialize_providers()}

    assert providers["groq"]["needs_base_url"] is False
    assert providers["zcode_glm"]["needs_base_url"] is False
    assert providers["groq"]["default_model"]
    assert providers["zcode_glm"]["default_model"]


def _client(monkeypatch, harness, *, demo: bool):
    monkeypatch.delenv("SOLO_API_TOKENS", raising=False)
    config = replace(harness.config, demo_mode=demo)
    monkeypatch.setattr(api_module, "_context", build_app(config, check_same_thread=False))
    monkeypatch.setattr(api_module, "_authenticator", None)
    monkeypatch.setattr(api_module, "_demo_sessions", {})
    monkeypatch.setattr(api_module, "reset_context", lambda: None)
    return TestClient(api_module.app, raise_server_exceptions=False)


def _demo_headers(client, name="Jayati"):
    token = client.post("/api/session/demo", json={"name": name}).json()["token"]
    return {"Authorization": f"Bearer {token}"}


def test_demo_session_is_refused_outside_demo_mode(monkeypatch, harness):
    client = _client(monkeypatch, harness, demo=False)

    assert client.get("/api/session").json()["demo_enabled"] is False
    assert client.post("/api/session/demo", json={"name": "x"}).status_code == 404
    assert client.get("/api/dashboard").status_code == 401


def test_demo_session_records_the_named_actor(monkeypatch, harness):
    client = _client(monkeypatch, harness, demo=True)
    headers = _demo_headers(client)

    body = client.post(
        "/api/runs", headers=headers,
        json={"order_id": "ORD-1001", "amount": 10, "task_class": "store_credit"},
    ).json()

    run = body["runs"][0]
    assert run["actor_id"] == "demo:jayati"
    assert run["task_class"] == "store_credit"
    assert set(body["licenses"]) == {"refund", "store_credit"}
    assert {p["key"] for p in body["providers"]} >= {"deterministic", "gemini", "openai_compatible"}
    assert body["economics"]["classes"][0]["supervision_cost_l0_month"] > 0


def test_unknown_task_class_is_a_422(monkeypatch, harness):
    client = _client(monkeypatch, harness, demo=True)
    headers = _demo_headers(client)

    response = client.post(
        "/api/runs", headers=headers, json={"order_id": "ORD-1001", "task_class": "wire"}
    )

    assert response.status_code == 422


def test_onboarding_validates_before_saving(monkeypatch, harness):
    client = _client(monkeypatch, harness, demo=True)
    headers = _demo_headers(client)

    bad = client.post(
        "/api/onboarding/complete", headers=headers,
        json={"business_name": "Acme", "starting_level": 9},
    )
    settings = client.get("/api/settings", headers=headers).json()

    assert bad.status_code == 422
    assert settings["onboarded"] is False


def test_payouts_share_one_remaining_balance(monkeypatch, harness):
    client = _client(monkeypatch, harness, demo=True)
    headers = _demo_headers(client)
    client.post("/api/runs", headers=headers,
                json={"order_id": "ORD-1001", "amount": 20, "task_class": "refund"})

    over = client.post("/api/runs", headers=headers,
                       json={"order_id": "ORD-1001", "amount": 10, "task_class": "store_credit"})

    assert over.status_code == 422
    assert "5.00" in over.json()["detail"]


def test_demo_session_survives_api_restart(monkeypatch, harness):
    client = _client(monkeypatch, harness, demo=True)
    headers = _demo_headers(client)
    api_module._demo_sessions.clear()  # what a process restart does

    assert client.get("/api/session/me", headers=headers).json()["id"] == "demo:jayati"


def test_dashboard_runs_carry_their_problems(monkeypatch, harness):
    client = _client(monkeypatch, harness, demo=True)
    headers = _demo_headers(client)
    client.post("/api/faults", headers=headers, json={"mode": "quiet_failure"})

    body = client.post("/api/runs", headers=headers, json={"order_id": "ORD-1001", "amount": 5}).json()

    assert body["runs"][0]["problems"] == ["state_mismatch"]


def test_inbox_webhook_needs_the_secret_and_returns_the_reply(monkeypatch, harness):
    client = _client(monkeypatch, harness, demo=True)
    headers = _demo_headers(client)
    secret = client.get("/api/inbox/secret", headers=headers).json()["secret"]
    message = {"from": "x", "email": "ada@example.com", "subject": "Broken", "body": "ORD-1001 is broken, refund please"}

    assert client.post("/api/inbox", json=message).status_code == 401
    assert client.post("/api/inbox?key=wrong", json=message).status_code == 401
    reply = client.post("/api/inbox", json=message, headers={"X-Solo-Inbox-Key": secret}).json()

    assert reply["status"] == "done" and "$25.00" in reply["reply"]
    tickets = client.get("/api/dashboard", headers=headers).json()["tickets"]
    assert tickets[0]["source"] == "webhook" and tickets[0]["steps"][0]["name"] == "read"


def test_paste_and_inbox_queue_are_handled_by_the_agent(monkeypatch, harness):
    client = _client(monkeypatch, harness, demo=True)
    headers = _demo_headers(client)

    pasted = client.post("/api/intake", headers=headers,
                         json={"message": "refund please", "sender": "alan@example.com"}).json()
    assert pasted["intake"]["status"] == "done" and pasted["intake"]["order_id"] == "ORD-1003"

    body = client.post("/api/tickets/handle-new", headers=headers).json()
    statuses = {t["sender"]: t["status"] for t in body["tickets"]}
    assert statuses["mallory@example.net"] == "needs_human"
    assert statuses["margaret@example.com"] == "declined"
    assert statuses["katherine@example.com"] == "waiting"


def test_csv_import_and_export(monkeypatch, harness):
    client = _client(monkeypatch, harness, demo=True)
    headers = _demo_headers(client)
    csv_text = "Order number,Customer,Email,Total,Date\nW-9001,Jo,jo@example.com,$19.99,2026-10-01\n"

    body = client.post("/api/orders/import", headers=headers, json={"csv": csv_text}).json()
    assert body["import"]["added"] == 1
    assert any(o["order_id"] == "W-9001" and o["source"] == "csv" for o in body["orders"])
    exported = client.get("/api/orders/export", headers=headers).text
    assert exported.splitlines()[0].startswith("order_id,customer,email") and "W-9001" in exported
    assert client.post("/api/orders/import", headers=headers, json={"csv": "a,b\n1,2"}).status_code == 422


def test_rejecting_a_draft_counts_against_the_job_type(monkeypatch, harness):
    client = _client(monkeypatch, harness, demo=True)
    headers = _demo_headers(client)
    body = client.post("/api/runs", headers=headers,
                       json={"order_id": "ORD-1004", "amount": 120, "task_class": "refund"}).json()
    run = body["runs"][0]
    assert run["status"] == "pending_approval"

    body = client.post(f"/api/runs/{run['id']}/reject", headers=headers).json()
    assert body["licenses"]["refund"]["failures"] == 1
    assert body["licenses"]["refund"]["progress"]["runs_needed"] is not None


def test_stripe_key_is_validated_before_saving(monkeypatch, harness):
    client = _client(monkeypatch, harness, demo=True)
    headers = _demo_headers(client)
    bad = client.put("/api/settings", headers=headers, json={"values": {"stripe_secret_key": "pk_test_123"}})
    live = client.put("/api/settings", headers=headers, json={"values": {"stripe_secret_key": "sk_live_123"}})
    assert bad.status_code == 422 and live.status_code == 422
