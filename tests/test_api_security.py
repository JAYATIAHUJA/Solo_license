from fastapi.testclient import TestClient

from app import api as api_module
from sololicense.bootstrap import AppContext, build_app


def _context_from_harness(harness) -> AppContext:
    return build_app(harness.config, check_same_thread=False)


def test_dashboard_requires_a_configured_bearer_token(monkeypatch, harness):
    monkeypatch.setenv(
        "SOLO_API_TOKENS",
        '{"operator-token":{"id":"ops-17","role":"operator"}}',
    )
    monkeypatch.setattr(api_module, "_context", _context_from_harness(harness))
    monkeypatch.setattr(api_module, "_authenticator", None, raising=False)
    client = TestClient(api_module.app, raise_server_exceptions=False)

    denied = client.get("/api/dashboard")
    allowed = client.get(
        "/api/dashboard", headers={"Authorization": "Bearer operator-token"}
    )

    assert denied.status_code == 401
    assert allowed.status_code == 200


def test_operator_cannot_restore_a_license(monkeypatch, harness):
    monkeypatch.setenv(
        "SOLO_API_TOKENS",
        '{"operator-token":{"id":"ops-17","role":"operator"}}',
    )
    monkeypatch.setattr(api_module, "_context", _context_from_harness(harness))
    monkeypatch.setattr(api_module, "_authenticator", None, raising=False)
    client = TestClient(api_module.app, raise_server_exceptions=False)

    response = client.post(
        "/api/restore",
        headers={"Authorization": "Bearer operator-token"},
        json={"level": 2, "reason": "reviewed"},
    )

    assert response.status_code == 403
