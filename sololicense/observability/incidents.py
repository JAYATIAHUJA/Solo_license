"""Which spans neatlogs should surface as incidents.

A coding trace records every decision, but only some of them mean the agent
lost trust or had to be stopped: a demotion, a person's flag, a loop the gate
halted, an interrupt after repeated forbidden attempts, a blocked forbidden or
policy-violating action. Guidance (a repeat warning, a failed tool the agent is
told how to undo) stays plain telemetry so the incident list keeps meaning
"a person should look at this".

Spans of other traces keep the old rule: every error is an incident.
"""

from __future__ import annotations

from typing import Any

_INCIDENT_SPANS = frozenset({"license.demote", "license.flag", "turn.flagged"})


def is_incident(trace_kind: str, name: str, status: str, attributes: dict[str, Any]) -> bool:
    if not trace_kind.startswith("coding."):
        return status == "error"
    if name in _INCIDENT_SPANS:
        return True
    if name.startswith("detection.") and attributes.get("severity") == "critical":
        return True
    return attributes.get("interrupt") is True


def incident_kind(name: str, attributes: dict[str, Any]) -> str:
    """Short label for the incident event: demote, flag, loop-stop, interrupt..."""
    if name.startswith("license."):
        return name.removeprefix("license.")
    if name == "turn.flagged":
        return "flag"
    if name == "detection.loop":
        return "loop-stop"
    if name.startswith("detection."):
        return name.removeprefix("detection.").replace("_", "-")
    if attributes.get("interrupt") is True:
        return "interrupt"
    return name
