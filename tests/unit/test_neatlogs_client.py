from __future__ import annotations

import sys
from dataclasses import replace
from types import SimpleNamespace

import pytest

from sololicense.observability import neatlogs_client
from sololicense.observability.neatlogs_client import init_neatlogs


@pytest.fixture(autouse=True)
def _fresh_sdk(monkeypatch):
    monkeypatch.setattr(neatlogs_client, "_ACTIVE_SDK", None)
    monkeypatch.setattr(neatlogs_client, "_ACTIVE_KEY", "")


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


def test_client_initializes_one_workflow_and_child_span(monkeypatch, harness):
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
        "workflow_name": "solo-license",
        "tags": [config.neatlogs_project, "neatHack"],
        "capture_logs": True,
    }]
    assert [(call["name"], call["kind"]) for call in calls] == [
        ("agent.run", "WORKFLOW"),
        ("verify.readback", "GUARDRAIL"),
    ]
    assert calls[0]["span"].attributes["sololicense.trace_id"] == "trace-local-1"
    assert calls[1]["span"].attributes == {
        "sololicense.status": "error",
        "sololicense.matched": False,
    }


def test_flushing_a_trace_closes_the_remote_workflow_once(harness):
    from sololicense.observability.tracer import Tracer

    closed: list[object] = []

    class _Client:
        def start_workflow(self, trace_id, attributes=None):
            return SimpleNamespace(trace_id="remote-1")

        def record_span(self, workflow, name, status, attributes):
            pass

        def finish_workflow(self, workflow):
            if workflow is not None:
                closed.append(workflow)

    trace = Tracer(_Client()).start_trace("permission", repo="shop-api")
    trace.flush(harness.conn, None)
    trace.close()

    assert trace.trace_id == "remote-1"
    assert len(closed) == 1
