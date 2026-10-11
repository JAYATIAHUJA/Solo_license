"""Links from a license event to where its story is told: the neatlogs trace."""

from __future__ import annotations

from collections.abc import Mapping

from sololicense.config import Config


def neatlogs_link(config: Config | None, trace_id: str | None) -> str | None:
    if config is None or not trace_id or not config.neatlogs_enabled:
        return None
    return f"{config.neatlogs_app_url.rstrip('/')}/traces/{trace_id}"


def event_payload(row: Mapping, config: Config | None) -> dict:
    """An ``agent_events`` row for the dashboard, with its neatlogs link."""
    event = dict(row)
    event["neatlogs_link"] = neatlogs_link(config, event.get("trace_id"))
    return event
