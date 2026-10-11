"""Lightweight tracing used from the first agent run.

A :class:`Trace` collects spans as the agent works, then flushes them to the
local SQLite mirror and forwards them to neatlogs. Keeping collection in memory
and flushing once means the run's ``run_id`` (assigned on insert) can be
stamped onto every span."""

from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass, field

from sololicense.db.repositories import spans as spans_repo
from sololicense.observability.incidents import is_incident
from sololicense.observability.neatlogs_client import NeatlogsClient


@dataclass
class Span:
    name: str
    attributes: dict
    status: str = "ok"


@dataclass
class Trace:
    """One gated run's worth of spans, identified by ``trace_id``."""

    trace_id: str
    client: NeatlogsClient
    spans: list[Span] = field(default_factory=list)
    remote_workflow: object | None = None
    kind: str = ""
    # Stamped on every span (e.g. repo / agent / principal of a coding turn).
    defaults: dict = field(default_factory=dict)

    def span(self, name: str, status: str = "ok", **attributes) -> None:
        """Record a step. Forwarded to neatlogs immediately; mirrored on flush."""
        attributes = {**self.defaults, **attributes}
        incident = None
        if self.kind.startswith("coding."):
            incident = is_incident(self.kind, name, status, attributes)
            if incident:
                attributes["incident"] = True
        self.spans.append(Span(name=name, attributes=attributes, status=status))
        self.client.record_span(self.remote_workflow, name, status, attributes, incident=incident)

    def flush(self, conn: sqlite3.Connection, run_id: int | None) -> None:
        """Persist every collected span to the local mirror. Caller commits."""
        for s in self.spans:
            spans_repo.insert_span(
                conn,
                trace_id=self.trace_id,
                run_id=run_id,
                name=s.name,
                attributes=s.attributes,
                status=s.status,
            )
        self.close()

    def close(self) -> None:
        """End the remote workflow exactly once, after local persistence."""
        self.client.finish_workflow(self.remote_workflow)
        self.remote_workflow = None


class Tracer:
    """Factory for traces, bound to a neatlogs client."""

    def __init__(self, client: NeatlogsClient) -> None:
        self._client = client

    def start_trace(self, name: str, *, defaults: dict | None = None, session_id: str | None = None,
                    **attributes) -> Trace:
        """``defaults`` go on every span of the trace; ``session_id`` groups
        traces of one agent session together in neatlogs."""
        local_id = uuid.uuid4().hex
        remote = self._client.start_workflow(local_id, {"task_class": name, **(defaults or {}), **attributes},
                                             session_id=session_id)
        # Prefer neatlogs' own trace id so the evidence packet deep-links to it.
        trace_id = (remote.trace_id if remote is not None else None) or local_id
        trace = Trace(trace_id=trace_id, client=self._client, remote_workflow=remote, kind=name,
                      defaults=dict(defaults or {}))
        trace.span("trace.start", kind=name, **attributes)
        return trace
