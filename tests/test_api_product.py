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
