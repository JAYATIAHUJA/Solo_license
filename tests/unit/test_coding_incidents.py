"""Which coding spans are incidents in neatlogs, and which are only telemetry."""

from __future__ import annotations

import pytest

from sololicense.observability.incidents import is_incident


@pytest.mark.parametrize("name, attributes", [
    ("license.demote", {"from_level": 2, "to_level": 0}),
    ("license.flag", {"from_level": 1, "to_level": 0}),
    ("turn.flagged", {"reason": "wrong package"}),
    ("detection.loop", {"severity": "critical", "interrupt": True}),
    ("detection.forbidden_action", {"severity": "critical"}),
    ("detection.policy_violation", {"severity": "critical"}),
    ("remediation.sent", {"kind": "denied", "interrupt": True}),
])
def test_lost_trust_loop_stops_and_interrupts_are_incidents(name, attributes):
    assert is_incident("coding.turn", name, "error", attributes) is True


@pytest.mark.parametrize("name, status, attributes", [
    ("license.promote", "ok", {"from_level": 0, "to_level": 1}),
    ("license.restore", "ok", {"from_level": 0, "to_level": 2}),
    ("license.policy", "ok", {}),
    ("detection.loop", "error", {"severity": "warning", "kind": "repeat"}),
    ("detection.edit_thrash", "error", {"severity": "warning"}),
    ("remediation.sent", "error", {"kind": "tool-failed"}),
    ("remediation.sent", "error", {"kind": "turn-failed"}),
    ("remediation.delivered", "ok", {"count": 1}),
    ("tool.failed", "error", {"action_class": "install-dep"}),
    ("turn.blocked", "error", {"reason": "tests failed"}),
    ("gate.deny", "error", {"decided_by": "hard-deny"}),
])
def test_guidance_and_ordinary_failures_are_not_incidents(name, status, attributes):
    assert is_incident("coding.turn", name, status, attributes) is False


def test_every_coding_trace_kind_uses_the_coding_rules():
    for kind in ("coding.flag", "coding.restore", "coding.policy"):
        assert is_incident(kind, "license.flag", "error", {}) is True
        assert is_incident(kind, "remediation.sent", "error", {"kind": "tool-failed"}) is False


def test_other_traces_keep_marking_every_error():
    assert is_incident("refund", "verify.readback", "error", {}) is True
    assert is_incident("refund", "tool.execute_refund", "ok", {}) is False
