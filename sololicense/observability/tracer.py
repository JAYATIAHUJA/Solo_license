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
from sololicense.observability.neatlogs_client import NeatlogsClient


@dataclass
class Span:
    name: str
    attributes: dict
    status: str = "ok"


@dataclass
class Trace:
    """One refund run's worth of spans, identified by ``trace_id``."""

    trace_id: str
    client: NeatlogsClient
    spans: list[Span] = field(default_factory=list)

    def span(self, name: str, status: str = "ok", **attributes) -> None:
        """Record a step. Forwarded to neatlogs immediately; mirrored on flush."""
        self.spans.append(Span(name=name, attributes=attributes, status=status))
        self.client.log_event(
            name, {"trace_id": self.trace_id, "status": status, **attributes}
        )

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


class Tracer:
    """Factory for traces, bound to a neatlogs client."""

    def __init__(self, client: NeatlogsClient) -> None:
        self._client = client

    def start_trace(self, name: str) -> Trace:
        trace = Trace(trace_id=uuid.uuid4().hex, client=self._client)
        trace.span("trace.start", kind=name)
        return trace
