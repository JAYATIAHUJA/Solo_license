from dataclasses import replace

from fastapi.testclient import TestClient

from sololicense.api import app as api_module
from sololicense.bootstrap import build_app


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


def test_demo_session_survives_api_restart(monkeypatch, harness):
    client = _client(monkeypatch, harness, demo=True)
    headers = _demo_headers(client)
    api_module._demo_sessions.clear()  # what a process restart does

    assert client.get("/api/session/me", headers=headers).json()["id"] == "demo:jayati"


def test_dashboard_is_only_settings_events_and_observability(monkeypatch, harness):
    client = _client(monkeypatch, harness, demo=True)
    headers = _demo_headers(client)
    context = api_module._context
    context.coding_gate.restore("shop-api", "test-run", 1, actor_id="demo:jayati", reason="reviewed")

    body = client.get("/api/dashboard", headers=headers).json()

    assert set(body) == {"settings", "events", "observability"}
    assert [(e["id"][:6], e["task_class"], e["kind"]) for e in body["events"]] == [
        ("agent-", "test-run@shop-api", "restore"),
    ]
    assert body["observability"]["ledger"]["repo"] == str(harness.repo)
    assert body["observability"]["ledger"]["events"] == 1
    assert not any("refund" in key or "stripe" in key for key in body["settings"])


def test_saving_the_neatlogs_project_round_trips(monkeypatch, harness):
    client = _client(monkeypatch, harness, demo=True)
    headers = _demo_headers(client)

    saved = client.put("/api/settings", headers=headers,
                       json={"values": {"neatlogs_project": "team-a", "business_name": "ignored"}})
    assert saved.status_code == 200
    assert set(saved.json()) == {"settings", "events", "observability"}
    # The real API rebuilds its context after saving; do the same here.
    monkeypatch.setattr(api_module, "_context",
                        build_app(replace(harness.config, demo_mode=True), check_same_thread=False))
    settings = client.get("/api/settings", headers=headers).json()

    assert settings["neatlogs_project"] == "team-a"
    assert "business_name" not in settings


def test_saved_secrets_are_masked_and_a_mask_keeps_the_stored_key(monkeypatch, harness):
    client = _client(monkeypatch, harness, demo=True)
    headers = _demo_headers(client)
    client.put("/api/settings", headers=headers, json={"values": {"typesafe_api_key": "ts-secret-1234"}})
    monkeypatch.setattr(api_module, "_context",
                        build_app(replace(harness.config, demo_mode=True), check_same_thread=False))

    client.put("/api/settings", headers=headers, json={"values": {"typesafe_api_key": "••••1234"}})
    monkeypatch.setattr(api_module, "_context",
                        build_app(replace(harness.config, demo_mode=True), check_same_thread=False))
    response = client.get("/api/settings", headers=headers)

    settings = response.json()
    assert settings["has_typesafe_api_key"] is True and settings["jev_enabled"] is True
    assert settings["typesafe_api_key_hint"] == "••••1234"
    assert "ts-secret-1234" not in response.text


def test_trust_confidence_out_of_range_is_a_422(monkeypatch, harness):
    client = _client(monkeypatch, harness, demo=True)
    headers = _demo_headers(client)

    response = client.put("/api/settings", headers=headers, json={"values": {"trust_confidence": 1.5}})

    assert response.status_code == 422


def test_payments_routes_are_gone(monkeypatch, harness):
    client = _client(monkeypatch, harness, demo=True)
    headers = _demo_headers(client)

    assert client.post("/api/runs", headers=headers, json={"order_id": "ORD-1001"}).status_code == 404
    assert client.post("/api/inbox", json={"body": "refund please"}).status_code == 404
    assert client.get("/api/policies", headers=headers).status_code == 404


def test_coding_dashboard_answers_on_an_empty_database(monkeypatch, harness):
    client = _client(monkeypatch, harness, demo=True)

    body = client.get("/api/coding").json()

    assert body["licenses"] == [] and body["events"] == []
    assert {c["key"] for c in body["classes"]} >= {"test-run"}
