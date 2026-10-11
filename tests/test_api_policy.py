from __future__ import annotations

from fastapi.testclient import TestClient

from app import api as api_module
from sololicense.bootstrap import build_app


def _client(monkeypatch, harness):
    monkeypatch.setenv(
        "SOLO_API_TOKENS",
        '{"operator-token":{"id":"ops-1","role":"operator"},'
        '"admin-token":{"id":"admin-1","role":"admin"}}',
    )
    monkeypatch.setattr(
        api_module, "_context", build_app(harness.config, check_same_thread=False)
    )
    monkeypatch.setattr(api_module, "_authenticator", None)
    monkeypatch.setattr(api_module, "_demo_sessions", {})
    return TestClient(api_module.app, raise_server_exceptions=False)


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _valid_policy() -> dict:
    return {
        "name": "Conservative support payouts",
        "summary": "Require three verified, clean runs per task class.",
        "rules": [
            {
                "task_class": "refund",
                "allowed_tool": "refund",
                "requires_approval_at_or_above": 1,
                "l2_ceiling": 40,
                "evaluation_window": 3,
                "minimum_samples": 3,
                "minimum_verified_pass_rate": 1,
            },
            {
                "task_class": "store_credit",
                "allowed_tool": "store_credit",
                "requires_approval_at_or_above": 1,
                "l2_ceiling": 60,
                "evaluation_window": 3,
                "minimum_samples": 3,
                "minimum_verified_pass_rate": 1,
            },
        ],
    }


def test_operator_cannot_activate_policy(monkeypatch, harness):
    client = _client(monkeypatch, harness)

    response = client.post(
        "/api/policies", headers=_headers("operator-token"), json=_valid_policy()
    )

    assert response.status_code == 403


def test_admin_preview_does_not_create_a_version(monkeypatch, harness):
    client = _client(monkeypatch, harness)

    preview = client.post(
        "/api/policies/preview", headers=_headers("admin-token"), json=_valid_policy()
    )
    policies = client.get("/api/policies", headers=_headers("admin-token"))

    assert preview.status_code == 200
    assert preview.json()["impacts"][0]["action"] == "hold_for_review"
    assert policies.json()["active"]["version"] == 1


def test_policy_activation_validates_complete_rules_and_serializes_progress(monkeypatch, harness):
    client = _client(monkeypatch, harness)
    incomplete = _valid_policy()
    incomplete["rules"] = incomplete["rules"][:1]

    invalid = client.post(
        "/api/policies", headers=_headers("admin-token"), json=incomplete
    )
    activated = client.post(
        "/api/policies", headers=_headers("admin-token"), json=_valid_policy()
    )
    dashboard = client.get("/api/dashboard", headers=_headers("admin-token"))

    assert invalid.status_code == 422
    assert activated.status_code == 200
    assert activated.json()["policy"]["version"] == 2
    assert dashboard.json()["policy"]["version"] == 2
    assert dashboard.json()["policy_evaluations"]["refund"]["sample_size"] == 0
