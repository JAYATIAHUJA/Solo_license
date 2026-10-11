"""The neatlogs Doctor probe must run in an isolated child process.

The API process keeps a live neatlogs tracer for agent traces; the Doctor
probe re-initialises the SDK with its own configuration, which the SDK
refuses in-process (-> BACKEND_PROBE_UNAVAILABLE). These tests pin the
contract of the isolated runner: secrets travel through the child
environment (never argv, never reports), the child emits one safe JSON
line, and every failure maps to a safe, structured report.
"""

from __future__ import annotations

import json
import subprocess
import sys
import types

import pytest

from sololicense.observability import neatlogs_probe


@pytest.fixture
def recorded_spawn(monkeypatch):
    """Replace the subprocess spawn with a recorder returning a pass report."""
    calls: list[dict] = []

    def _spawn(argv, env, timeout):
        calls.append({"argv": list(argv), "env": dict(env), "timeout": timeout})
        result = types.SimpleNamespace(returncode=0, stdout=json.dumps({
            "format_version": "neatlogs.doctor/v2", "mode": "probe",
            "status": "pass", "first_failure": None, "checks": [],
        }), stderr="")
        return result

    monkeypatch.setattr(neatlogs_probe, "_spawn", _spawn)
    return calls


# --- how the child is invoked ---------------------------------------------


def test_probe_spawns_an_isolated_child(recorded_spawn):
    report = neatlogs_probe.run_doctor_probe("nlk-secret-key", "https://ingest.neatlogs.com")
    assert report["status"] == "pass"
    assert len(recorded_spawn) == 1
    argv = recorded_spawn[0]["argv"]
    assert argv[0] == sys.executable
    assert "-I" in argv  # isolated: no user site, no PYTHON* env influence
    assert "-c" in argv  # inline code, not a predictable script path


def test_probe_secrets_never_travel_on_the_command_line(recorded_spawn):
    neatlogs_probe.run_doctor_probe("nlk-secret-key", "https://ingest.neatlogs.com")
    argv = recorded_spawn[0]["argv"]
    assert not any("nlk-secret-key" in part for part in argv)
    env = recorded_spawn[0]["env"]
    assert env[neatlogs_probe.KEY_ENV] == "nlk-secret-key"
    assert env[neatlogs_probe.ENDPOINT_ENV] == "https://ingest.neatlogs.com"


def test_probe_gives_the_child_a_bounded_timeout(recorded_spawn):
    neatlogs_probe.run_doctor_probe("nlk-secret-key", "https://ingest.neatlogs.com")
    # 45s matches the neatlogs Doctor's own default read-back budget.
    assert recorded_spawn[0]["timeout"] >= 45.0


# --- the child code itself -------------------------------------------------


def test_child_code_calls_the_doctor_with_environment_values(monkeypatch, capsys):
    stub = types.ModuleType("neatlogs")
    seen: dict = {}

    def doctor_probe_v2(*, api_key, endpoint, timeout_seconds):
        seen.update(api_key=api_key, endpoint=endpoint, timeout=timeout_seconds)
        return {"status": "pass", "probe": True}

    stub.doctor_probe_v2 = doctor_probe_v2
    monkeypatch.setitem(sys.modules, "neatlogs", stub)
    monkeypatch.setenv(neatlogs_probe.KEY_ENV, "nlk-env-key")
    monkeypatch.setenv(neatlogs_probe.ENDPOINT_ENV, "https://ingest.neatlogs.com")
    monkeypatch.setenv(neatlogs_probe.TIMEOUT_ENV, "45")

    exec(compile(neatlogs_probe.CHILD_CODE, "<probe-child>", "exec"), {})

    assert seen == {
        "api_key": "nlk-env-key",
        "endpoint": "https://ingest.neatlogs.com",
        "timeout": 45.0,
    }
    assert json.loads(capsys.readouterr().out) == {"status": "pass", "probe": True}


# --- failure paths ---------------------------------------------------------


def test_probe_timeout_returns_a_safe_structured_report(monkeypatch):
    def _spawn(argv, env, timeout):
        raise subprocess.TimeoutExpired(cmd=argv, timeout=timeout)

    monkeypatch.setattr(neatlogs_probe, "_spawn", _spawn)
    report = neatlogs_probe.run_doctor_probe("nlk-secret-key", "https://ingest.neatlogs.com")
    assert report["status"] == "fail"
    assert report["first_failure"] == "PROBE_TIMEOUT"
    assert "nlk-secret-key" not in json.dumps(report)


def test_probe_crashed_child_returns_safe_diagnostics(monkeypatch):
    def _spawn(argv, env, timeout):
        return types.SimpleNamespace(
            returncode=3,
            stdout="",
            stderr="Traceback … NeatlogsConfigurationError: nlk-secret-key",
        )

    monkeypatch.setattr(neatlogs_probe, "_spawn", _spawn)
    report = neatlogs_probe.run_doctor_probe("nlk-secret-key", "https://ingest.neatlogs.com")
    assert report["status"] == "fail"
    assert report["first_failure"] == "BACKEND_PROBE_UNAVAILABLE"
    blob = json.dumps(report)
    assert "nlk-secret-key" not in blob
    assert "3" in report.get("diagnostics", "")


def test_probe_scrubs_a_secret_leaked_by_the_report(monkeypatch):
    leaked = json.dumps({
        "status": "fail", "first_failure": "AUTH_FAILED",
        "checks": [{"name": "auth", "message": "key nlk-secret-key rejected"}],
    })

    def _spawn(argv, env, timeout):
        return types.SimpleNamespace(returncode=0, stdout=leaked, stderr="")

    monkeypatch.setattr(neatlogs_probe, "_spawn", _spawn)
    report = neatlogs_probe.run_doctor_probe("nlk-secret-key", "https://ingest.neatlogs.com")
    assert "nlk-secret-key" not in json.dumps(report)
    assert report["first_failure"] == "AUTH_FAILED"


# --- API response mapping ----------------------------------------------------


def test_response_pass():
    out = neatlogs_probe.response_for({
        "status": "pass", "first_failure": None, "checks": [],
    })
    assert out["ok"] is True and out["code"] == "PASS"


def test_response_trace_accepted_but_still_processing_is_a_soft_success():
    out = neatlogs_probe.response_for({
        "status": "fail", "first_failure": "TRACE_READBACK_TIMEOUT",
        "checks": [{"details": {"last_successful_stage": "exported"}}],
    })
    assert out["ok"] is True
    assert out["code"] == "TRACE_READBACK_TIMEOUT"
    assert "processing" in out["message"].lower()


@pytest.mark.parametrize("code", ["AUTH_FAILED"])
def test_response_auth_failure_is_actionable(code):
    out = neatlogs_probe.response_for({
        "status": "fail", "first_failure": code, "checks": [],
    })
    assert out["ok"] is False and out["code"] == code
    assert "key" in out["message"].lower()


@pytest.mark.parametrize("code", ["BACKEND_CONNECTION_FAILED", "BACKEND_HTTP_ERROR", "ENDPOINT_INVALID"])
def test_response_network_failures_point_at_the_endpoint(code):
    out = neatlogs_probe.response_for({
        "status": "fail", "first_failure": code, "checks": [],
    })
    assert out["ok"] is False and out["code"] == code
    assert "reach" in out["message"].lower() or "address" in out["message"].lower()


@pytest.mark.parametrize("code", ["BACKEND_PROBE_UNAVAILABLE", "PROBE_TIMEOUT"])
def test_response_probe_failures_do_not_blame_the_key(code):
    out = neatlogs_probe.response_for({
        "status": "fail", "first_failure": code, "checks": [],
    })
    assert out["ok"] is False and out["code"] == code
    assert "try again" in out["message"].lower()


def test_response_unknown_code_fails_safe_with_the_code_preserved():
    out = neatlogs_probe.response_for({
        "status": "fail", "first_failure": "SOMETHING_NEW", "checks": [],
    })
    assert out["ok"] is False and out["code"] == "SOMETHING_NEW"
