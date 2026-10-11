"""Run the neatlogs Doctor probe in an isolated child process.

Why a child process: the API process keeps a live neatlogs tracer for agent
traces. The Doctor probe re-initialises the SDK with its own diagnostic
configuration, which the SDK refuses in-process
(``NeatlogsConfigurationError`` -> ``BACKEND_PROBE_UNAVAILABLE``), and we
must never shut down or reinitialise the live tracer just to test a key.

The contract here:

* credentials travel to the child through its environment - never on the
  command line, never in logs, and never back in the report;
* the child prints exactly one JSON line (the Doctor report) and exits;
* the parent bounds the whole run (the Doctor's own read-back budget is
  45s, so the app must not impose a shorter one);
* every failure maps to a safe, structured response the frontend can turn
  into actionable guidance.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import Any

# The Doctor's intended read-back budget (its own default). Shorter app-side
# timeouts report transient "unavailable" failures on slow-but-healthy days.
PROBE_TIMEOUT_SECONDS = 45.0

KEY_ENV = "SOLO_PROBE_API_KEY"
ENDPOINT_ENV = "SOLO_PROBE_ENDPOINT"
TIMEOUT_ENV = "SOLO_PROBE_TIMEOUT_SECONDS"

# Runs with ``python -I -c CHILD_CODE``: isolated mode keeps user site and
# PYTHON* variables out, so the child imports exactly the venv's neatlogs.
CHILD_CODE = """
import json, os, sys

import neatlogs

try:
    report = neatlogs.doctor_probe_v2(
        api_key=os.environ["SOLO_PROBE_API_KEY"],
        endpoint=os.environ["SOLO_PROBE_ENDPOINT"],
        timeout_seconds=float(os.environ.get("SOLO_PROBE_TIMEOUT_SECONDS", "45")),
    )
except Exception as error:  # the parent maps any child crash to a safe code
    report = {
        "format_version": "neatlogs.doctor/v2",
        "mode": "probe",
        "status": "fail",
        "first_failure": "BACKEND_PROBE_UNAVAILABLE",
        "checks": [{"name": "child", "message": f"{type(error).__name__}"}],
    }
sys.stdout.write(json.dumps(report))
sys.stdout.flush()
"""

_MASK = "••••"


def _spawn(argv: list[str], env: dict[str, str], timeout: float):
    """Run the probe child. Split out so tests can intercept the boundary."""
    return subprocess.run(
        argv, env=env, capture_output=True, text=True, timeout=timeout, check=False
    )


def _scrub(value: Any, secret: str) -> Any:
    """Remove every occurrence of the secret from a JSON-able structure."""
    if not secret:
        return value
    try:
        return json.loads(json.dumps(value).replace(secret, _MASK))
    except (TypeError, ValueError):
        return {"status": "fail", "first_failure": "BACKEND_PROBE_UNAVAILABLE"}


def _failure(first_failure: str, diagnostics: str = "") -> dict[str, Any]:
    report: dict[str, Any] = {
        "format_version": "neatlogs.doctor/v2",
        "mode": "probe",
        "status": "fail",
        "first_failure": first_failure,
        "checks": [],
    }
    if diagnostics:
        report["diagnostics"] = diagnostics[:300]
    return report


def run_doctor_probe(
    api_key: str, endpoint: str, timeout_seconds: float = PROBE_TIMEOUT_SECONDS
) -> dict[str, Any]:
    """Doctor-probe neatlogs out of process; return a safe report dict.

    Never raises: every failure mode - timeout, crash, unparseable output -
    comes back as a structured ``{"status": "fail", "first_failure": ...}``
    report with the secret scrubbed.
    """
    env = os.environ.copy()
    env[KEY_ENV] = api_key
    env[ENDPOINT_ENV] = endpoint
    env[TIMEOUT_ENV] = str(timeout_seconds)
    try:
        completed = _spawn(
            [sys.executable, "-I", "-c", CHILD_CODE],
            env,
            timeout_seconds + 10.0,  # child budget plus process overhead
        )
    except subprocess.TimeoutExpired:
        return _scrub(
            _failure("PROBE_TIMEOUT", "probe child did not finish within its budget"),
            api_key,
        )
    stdout = (completed.stdout or "").strip()
    if not stdout:
        stderr = (completed.stderr or "").strip().splitlines()
        detail = stderr[-1][:200] if stderr else ""
        return _scrub(
            _failure(
                "BACKEND_PROBE_UNAVAILABLE",
                f"probe child exited with code {completed.returncode}: {detail}",
            ),
            api_key,
        )
    try:
        report = json.loads(stdout.splitlines()[-1])
    except ValueError:
        return _scrub(
            _failure(
                "BACKEND_PROBE_UNAVAILABLE",
                f"probe child returned unparseable output (code {completed.returncode})",
            ),
            api_key,
        )
    if not isinstance(report, dict):
        return _scrub(
            _failure("BACKEND_PROBE_UNAVAILABLE", "probe child returned no report object"),
            api_key,
        )
    # Defense in depth: even if the report echoed the credential, it must
    # never cross back to the API response.
    return _scrub(report, api_key)


_MESSAGES = {
    "AUTH_FAILED": "neatlogs did not accept that API key. Copy the whole key from your neatlogs account and try again.",
    "CREDENTIAL_MISSING": "Add a neatlogs API key first.",
    "TRACE_READBACK_TIMEOUT": "Connected. neatlogs accepted the probe trace, but it is still processing - check your neatlogs Traces page in a minute, or run the test again.",
    "BACKEND_CONNECTION_FAILED": "Could not reach neatlogs at that address. Check the service address and your internet connection.",
    "BACKEND_HTTP_ERROR": "neatlogs answered with an error. Check the service address, or neatlogs status, and try again.",
    "ENDPOINT_INVALID": "That neatlogs service address is not valid. Keep the standard https://ingest.neatlogs.com unless neatlogs told you otherwise.",
    "BACKEND_PROBE_UNAVAILABLE": "The diagnostic probe could not complete - this is a probe issue, not proof your key or network is wrong. Try again in a moment.",
    "PROBE_TIMEOUT": "The diagnostic probe did not finish in time - neatlogs may be busy. Try again in a minute.",
}


def response_for(report: dict[str, Any], secret: str = "") -> dict[str, Any]:
    """Turn a Doctor report into the API's safe, structured test response.

    ``secret`` (the tested API key) is scrubbed defensively from every
    returned field, so a report that echoed the credential upstream can
    never reach the browser.
    """
    if report.get("status") == "pass":
        return {
            "ok": True,
            "code": "PASS",
            "message": "Connected. neatlogs accepted the probe trace and read it back - your key and the trace pipeline both work.",
        }
    code = str(report.get("first_failure") or "UNKNOWN")
    checks = report.get("checks") or []
    accepted = any(
        (check.get("details") or {}).get("last_successful_stage") for check in checks
    )
    soft_ok = code == "TRACE_READBACK_TIMEOUT" and accepted
    if soft_ok:
        message = _MESSAGES["TRACE_READBACK_TIMEOUT"]
    elif code in _MESSAGES:
        message = _MESSAGES[code]
    else:
        message = "neatlogs did not pass the test. Nothing looks wrong locally - try again, or check neatlogs status."
    detail = next(
        (str(check.get("message", "")) for check in checks if check.get("message")),
        "",
    )[:200]
    response = {
        "ok": soft_ok,
        "code": code,
        "message": message,
        "detail": detail or str(report.get("diagnostics", ""))[:200],
    }
    return _scrub(response, secret) if secret else response
