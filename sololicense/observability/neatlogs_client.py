"""neatlogs SDK adapter.

Initialised once, before any agent logic, per the hackathon requirement. The
adapter is defensive: if the ``neatlogs`` package or an API key is missing it
returns a disabled client, and the tracer falls back to the local SQLite span
mirror. This guarantees the demo runs end-to-end in any environment while
still shipping real traces + detections when a key is present.

Mapping (documented for judges)
--------------------------------
* A *trace* groups the spans of one refund run and carries a ``trace_id``.
* A *span* is one step (plan / check-license / execute / verify) with
  attributes such as before/after refunded amounts.
* A *detection* is a tagged event on the trace with a severity; our custom
  rules (state_mismatch, missing_verification, policy_breach) emit these.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sololicense.config import Config


@dataclass
class NeatlogsClient:
    """Handle to the neatlogs SDK, or a disabled stand-in."""

    enabled: bool
    project: str
    _sdk: object | None = None

    def start_workflow(
        self, trace_id: str, attributes: dict[str, Any] | None = None
    ) -> "NeatlogsWorkflow | None":
        """Open the remote root for one licensed run."""
        if not self.enabled or self._sdk is None:
            return None
        try:  # pragma: no cover - requires live SDK + key
            task_class = str((attributes or {}).get("task_class", "refund"))
            context = self._sdk.trace(f"{task_class}.run", kind="WORKFLOW")
            root = context.__enter__()
            root.set_attribute("sololicense.trace_id", trace_id)
            for key, value in _safe_attributes(attributes or {}).items():
                root.set_attribute(f"sololicense.{key}", value)
            return NeatlogsWorkflow(context=context, root=root)
        except Exception:
            return None

    def record_span(
        self,
        workflow: "NeatlogsWorkflow | None",
        name: str,
        status: str,
        attributes: dict[str, Any],
    ) -> None:
        """Emit one safe child span inside the active refund workflow."""
        if workflow is None or not self.enabled or self._sdk is None:
            return
        try:  # pragma: no cover - requires live SDK + key
            with self._sdk.trace(name, kind=_span_kind(name)) as span:
                span.set_attribute("sololicense.status", status)
                for key, value in _safe_attributes(attributes).items():
                    span.set_attribute(f"sololicense.{key}", value)
                if status == "error":
                    _mark_error(span, str(attributes.get("message", name)))
        except Exception:
            return

    def finish_workflow(self, workflow: "NeatlogsWorkflow | None") -> None:
        """Close a root; long-running servers export in the SDK background."""
        if workflow is None:
            return
        try:  # pragma: no cover - requires live SDK + key
            workflow.context.__exit__(None, None, None)
        except Exception:
            return

    def shutdown(self) -> None:
        """Flush and stop the SDK once at server shutdown."""
        if not self.enabled or self._sdk is None:
            return
        try:  # pragma: no cover - requires live SDK + key
            self._sdk.shutdown()
        except Exception:
            return


@dataclass
class NeatlogsWorkflow:
    context: Any
    root: Any

    @property
    def trace_id(self) -> str | None:
        """The OpenTelemetry trace id neatlogs indexes this run under."""
        try:  # pragma: no cover - requires live SDK
            value = self.root.get_span_context().trace_id
            return f"{value:032x}" if value else None
        except Exception:
            return None


def _mark_error(span: Any, message: str) -> None:
    """Flag the span as failed so neatlogs surfaces it as an error/incident."""
    try:  # pragma: no cover - requires the OpenTelemetry SDK span
        from opentelemetry.trace import Status, StatusCode

        span.set_status(Status(StatusCode.ERROR, message[:200]))
    except Exception:
        return


def _span_kind(name: str) -> str:
    if name == "plan":
        return "AGENT"
    if name.startswith("tool."):
        return "TOOL"
    if name.startswith(("license.", "verify.", "detection.")):
        return "GUARDRAIL"
    return "CHAIN"


def _safe_attributes(attributes: dict[str, Any]) -> dict[str, str | bool | int | float]:
    """Keep telemetry scalar and ensure configuration secrets never export."""
    safe: dict[str, str | bool | int | float] = {}
    for key, value in attributes.items():
        if any(secret in key.lower() for secret in ("api_key", "token", "password", "secret")):
            continue
        if isinstance(value, (str, bool, int, float)):
            safe[key] = value
    return safe


_ACTIVE_SDK: Any = None
_ACTIVE_KEY: str = ""


def wrap_llm_client(client: Any) -> Any:
    """Auto-trace an LLM client's calls when neatlogs is live; else unchanged."""
    if _ACTIVE_SDK is None:
        return client
    try:  # pragma: no cover - requires live SDK + key
        return _ACTIVE_SDK.wrap(client)
    except Exception:
        return client


def init_neatlogs(config: Config) -> NeatlogsClient:
    """Initialise neatlogs before agent logic. Safe with no key/package."""
    if not config.neatlogs_enabled:
        return NeatlogsClient(enabled=False, project=config.neatlogs_project)

    try:  # pragma: no cover - requires the optional dependency + key
        import neatlogs  # type: ignore

        global _ACTIVE_SDK, _ACTIVE_KEY
        init = getattr(neatlogs, "init", None)
        if callable(init) and _ACTIVE_KEY != config.neatlogs_api_key:
            # init() is process-wide: settings rebuilds reuse the exporter and
            # only a changed key flushes it and starts a fresh one.
            if _ACTIVE_SDK is not None:
                _ACTIVE_SDK.shutdown()
            init(
                api_key=config.neatlogs_api_key,
                endpoint=config.neatlogs_endpoint,
                workflow_name="solo-license",
                tags=[config.neatlogs_project, "neatHack"],
                capture_logs=True,
            )
        _ACTIVE_SDK, _ACTIVE_KEY = neatlogs, config.neatlogs_api_key
        return NeatlogsClient(
            enabled=True, project=config.neatlogs_project, _sdk=neatlogs
        )
    except Exception:  # pragma: no cover - fall back to local mirror
        return NeatlogsClient(enabled=False, project=config.neatlogs_project)
