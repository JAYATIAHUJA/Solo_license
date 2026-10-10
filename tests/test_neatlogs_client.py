from __future__ import annotations

import sys
from dataclasses import replace
from types import SimpleNamespace

import pytest

from sololicense.domain.models import RefundRequest
from sololicense.observability.neatlogs_client import init_neatlogs


class _Span:
    def __init__(self) -> None:
        self.attributes: dict[str, object] = {}

    def set_attribute(self, key: str, value: object) -> None:
        self.attributes[key] = value


class _TraceContext:
    def __init__(self, calls: list[dict], **call: object) -> None:
        self._calls = calls
        self._call = call
        self.span = _Span()

    def __enter__(self) -> _Span:
        self._calls.append({**self._call, "span": self.span})
        return self.span

    def __exit__(self, exc_type, exc, traceback) -> None:
        self._call["exit"] = exc_type


def test_client_initializes_one_refund_workflow_and_child_span(monkeypatch, harness):
    calls: list[dict] = []
    init_calls: list[dict] = []

    def trace(name: str, **kwargs: object) -> _TraceContext:
        return _TraceContext(calls, name=name, **kwargs)

    fake_sdk = SimpleNamespace(
        init=lambda **kwargs: init_calls.append(kwargs),
        trace=trace,
        flush_all=lambda: {"default": True},
    )
    monkeypatch.setitem(sys.modules, "neatlogs", fake_sdk)
    config = replace(harness.config, neatlogs_api_key="project-key")

    client = init_neatlogs(config)
    remote = client.start_workflow("trace-local-1")
    client.record_span(remote, "verify.readback", "error", {"matched": False})
    client.finish_workflow(remote)

    assert client.enabled is True
    assert init_calls == [{
        "api_key": "project-key",
        "endpoint": "https://ingest.neatlogs.com",
        "workflow_name": "refund-agent",
        "capture_logs": True,
    }]
    assert [(call["name"], call["kind"]) for call in calls] == [
        ("refund.run", "WORKFLOW"),
        ("verify.readback", "GUARDRAIL"),
    ]
    assert calls[0]["span"].attributes["sololicense.trace_id"] == "trace-local-1"
    assert calls[1]["span"].attributes == {
        "sololicense.status": "error",
        "sololicense.matched": False,
    }


class _TraceSpy:
    def __init__(self) -> None:
        self.trace_id = "trace-spy"
        self.spans: list[tuple[str, str, dict]] = []
        self.closed = False

    def span(self, name: str, status: str = "ok", **attributes: object) -> None:
        self.spans.append((name, status, attributes))

    def close(self) -> None:
        self.closed = True


class _TracerSpy:
    def __init__(self) -> None:
        self.trace = _TraceSpy()

    def start_trace(self, name: str) -> _TraceSpy:
        assert name == "refund"
        return self.trace


def test_refund_failure_closes_the_remote_workflow(monkeypatch, harness):
    tracer = _TracerSpy()
    monkeypatch.setattr(harness.worker, "_tracer", tracer)

    def fail_plan(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("planner unavailable")

    monkeypatch.setattr(harness.worker._planner, "plan", fail_plan)

    with pytest.raises(RuntimeError, match="planner unavailable"):
        harness.worker.run_refund(RefundRequest("ORD-1001", "Asha", 10.0, "refund"))

    assert tracer.trace.closed is True
    assert tracer.trace.spans[-1] == (
        "run.error", "error", {"error_type": "RuntimeError"}
    )
