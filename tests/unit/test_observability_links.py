"""Deep links from a coding event to its neatlogs trace."""

from __future__ import annotations

from dataclasses import replace

from sololicense.config import load_config
from sololicense.observability.links import event_payload, neatlogs_link


def _config(**overrides):
    return replace(load_config(), **overrides)


def test_link_uses_the_app_url_and_trace_id():
    config = _config(neatlogs_api_key="k", neatlogs_app_url="https://app.neatlogs.com/")
    assert neatlogs_link(config, "abc123") == "https://app.neatlogs.com/traces/abc123"


def test_no_link_without_neatlogs_or_without_a_trace():
    assert neatlogs_link(_config(neatlogs_api_key=""), "abc123") is None
    assert neatlogs_link(_config(neatlogs_api_key="k"), None) is None
    assert neatlogs_link(_config(neatlogs_api_key="k"), "") is None
    assert neatlogs_link(None, "abc123") is None


def test_event_payload_adds_the_link_and_keeps_every_column():
    row = {"id": 3, "kind": "demote", "trace_id": "t1", "entire_checkpoint": "a3b2c4d5e6f7", "git_sha": "abc1234"}
    out = event_payload(row, _config(neatlogs_api_key="k", neatlogs_app_url="https://app.neatlogs.com"))
    assert out == {**row, "neatlogs_link": "https://app.neatlogs.com/traces/t1"}
    assert event_payload(row, _config(neatlogs_api_key=""))["neatlogs_link"] is None
