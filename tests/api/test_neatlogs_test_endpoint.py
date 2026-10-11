"""/api/settings/test-neatlogs must probe from an isolated child process.

The regression these tests guard against: calling the Doctor probe in the
API process re-initialises the live neatlogs tracer, which the SDK refuses
(BACKEND_PROBE_UNAVAILABLE). The endpoint must leave the in-process SDK
untouched, run the probe out of process, and answer with structured, safe
diagnostics the frontend can act on.
"""

from __future__ import annotations

from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from sololicense.api import app as api_module
from sololicense.bootstrap import AppContext, build_app


def _client(monkeypatch, harness) -> TestClient:
    monkeypatch.delenv("SOLO_API_TOKENS", raising=False)
    context = build_app(
        replace(harness.config, demo_mode=True), check_same_thread=False
    )
    monkeypatch.setattr(api_module, "_context", context)
    monkeypatch.setattr(api_module, "_authenticator", None, raising=False)
    monkeypatch.setattr(api_module, "_demo_sessions", {})
    monkeypatch.setattr(api_module, "reset_context", lambda: None)
    client = TestClient(api_module.app, raise_server_exceptions=False)
    return client


def _demo_headers(client) -> dict:
    token = client.post("/api/session/demo", json={"name": "Probe Tester"}).json()["token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def guard_live_sdk(monkeypatch):
    """Fail the request if the endpoint touches the in-process neatlogs SDK."""
    import neatlogs

    def _forbidden(*args, **kwargs):
        raise AssertionError("the live tracer must not be re-initialised or shut down")

    monkeypatch.setattr(neatlogs, "init", _forbidden, raising=False)
    monkeypatch.setattr(neatlogs, "shutdown", _forbidden, raising=False)


def test_probe_does_not_touch_the_live_tracer(monkeypatch, harness, guard_live_sdk):
    client = _client(monkeypatch, harness)
    headers = _demo_headers(client)
    monkeypatch.setattr(
        api_module, "run_doctor_probe",
        lambda key, endpoint: {"status": "pass", "first_failure": None, "checks": []},
    )
    response = client.post(
        "/api/settings/test-neatlogs",
        json={"values": {"neatlogs_api_key": "nlk-form-key"}},
        headers=headers,
    )
    assert response.status_code == 200  # the guarded init/shutdown never fired
    body = response.json()
    assert body["ok"] is True and body["code"] == "PASS"


def test_probe_failure_returns_structured_safe_diagnostics(monkeypatch, harness, guard_live_sdk):
    client = _client(monkeypatch, harness)
    headers = _demo_headers(client)
    monkeypatch.setattr(
        api_module, "run_doctor_probe",
        lambda key, endpoint: {
            "status": "fail", "first_failure": "AUTH_FAILED",
            "checks": [{"name": "auth", "message": f"key {key} rejected"}],
        },
    )
    response = client.post(
        "/api/settings/test-neatlogs",
        json={"values": {"neatlogs_api_key": "nlk-form-key"}},
        headers=headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert body["code"] == "AUTH_FAILED"
    assert "key" in body["message"].lower()
    assert "nlk-form-key" not in response.text


def test_probe_without_a_key_says_so(monkeypatch, harness, guard_live_sdk):
    client = _client(monkeypatch, harness)
    headers = _demo_headers(client)
    monkeypatch.setattr(
        api_module, "run_doctor_probe",
        lambda key, endpoint: pytest.fail("must not run without a key"),
    )
    response = client.post(
        "/api/settings/test-neatlogs", json={"values": {"neatlogs_project": "x"}},
        headers=headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False and body["code"] == "CREDENTIAL_MISSING"


def test_probe_ignores_a_masked_form_value_when_nothing_is_saved(monkeypatch, harness, guard_live_sdk):
    client = _client(monkeypatch, harness)
    headers = _demo_headers(client)
    seen: dict = {}
    monkeypatch.setattr(
        api_module, "run_doctor_probe",
        lambda key, endpoint: seen.update(key=key) or {
            "status": "pass", "first_failure": None, "checks": [],
        },
    )
    # A masked form value means "keep the stored secret"; none is stored in
    # this fresh harness, so the endpoint must not probe at all.
    response = client.post(
        "/api/settings/test-neatlogs",
        json={"values": {"neatlogs_api_key": "••••abcd"}},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["code"] == "CREDENTIAL_MISSING"
    assert seen == {}


def test_probe_soft_success_when_trace_still_processing(monkeypatch, harness, guard_live_sdk):
    client = _client(monkeypatch, harness)
    headers = _demo_headers(client)
    monkeypatch.setattr(
        api_module, "run_doctor_probe",
        lambda key, endpoint: {
            "status": "fail", "first_failure": "TRACE_READBACK_TIMEOUT",
            "checks": [{"details": {"last_successful_stage": "exported"}}],
        },
    )
    response = client.post(
        "/api/settings/test-neatlogs",
        json={"values": {"neatlogs_api_key": "nlk-form-key"}},
        headers=headers,
    )
    body = response.json()
    assert body["ok"] is True and body["code"] == "TRACE_READBACK_TIMEOUT"
