"""Spend adapters: one per agent, each fed the shape that agent really writes."""

from __future__ import annotations

import json

import pytest

from sololicense.coding import budget
from sololicense.coding.agents import AGENTS


def _jsonl(path, *records):
    path.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
    return str(path)


def _claude_line(msg_id, model, inp, out, read=0, write=0):
    return {"type": "assistant", "requestId": f"req_{msg_id}",
            "message": {"id": msg_id, "model": model, "role": "assistant",
                        "usage": {"input_tokens": inp, "output_tokens": out, "cache_read_input_tokens": read,
                                  "cache_creation_input_tokens": write}}}


# --- Claude Code ------------------------------------------------------------------

def test_claude_transcript_counts_each_message_once(tmp_path):
    """Claude Code writes one line per content block, each repeating the message's usage."""
    path = _jsonl(tmp_path / "s.jsonl",
                  {"type": "user", "message": {"role": "user", "content": "fix it"}},
                  _claude_line("msg_1", "claude-sonnet-4-5-20250929", 10, 5, read=1000, write=200),
                  _claude_line("msg_1", "claude-sonnet-4-5-20250929", 10, 50, read=1000, write=200),
                  _claude_line("msg_2", "claude-sonnet-4-5-20250929", 20, 100, read=2000),
                  _claude_line("msg_3", "<synthetic>", 0, 0))

    spend = budget.usage_from_transcript("claude-code", path)

    t = spend.tokens["claude-sonnet-4-5-20250929"]
    assert (t.input, t.output, t.cache_read, t.cache_write) == (30, 150, 3000, 200)
    usd, unpriced = budget.estimate(spend)
    # sonnet: $3 in, $15 out, $0.30 cache read, $3.75 cache write per million
    assert usd == pytest.approx((30 * 3 + 150 * 15 + 3000 * 0.3 + 200 * 3.75) / 1e6)
    assert unpriced == []


def test_transcripts_are_read_incrementally_and_survive_a_half_written_line(tmp_path):
    path = tmp_path / "s.jsonl"
    _jsonl(path, _claude_line("msg_1", "claude-opus-4-6", 100, 10))
    first = budget.usage_from_transcript("claude-code", str(path))
    assert first.total().input == 100
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(_claude_line("msg_2", "claude-opus-4-6", 50, 5)) + "\n")
        f.write('{"type": "assistant", "message": {"id": "msg_3"')   # still being written
    second = budget.usage_from_transcript("claude-code", str(path))
    assert second.total().input == 150
    with path.open("a", encoding="utf-8") as f:
        f.write(', "model": "claude-opus-4-6", "usage": {"input_tokens": 7, "output_tokens": 1}}}\n')
    assert budget.usage_from_transcript("claude-code", str(path)).total().input == 157


def test_claude_statusline_is_claude_codes_own_cost():
    report = budget.report_from("claude-code", {
        "session_id": "abc", "transcript_path": "/tmp/abc.jsonl",
        "model": {"id": "claude-opus-4-6", "display_name": "Opus"},
        "workspace": {"current_dir": "/work/shop-api", "project_dir": "/work/shop-api"},
        "cost": {"total_cost_usd": 1.2345, "total_duration_ms": 4000},
    })
    assert (report.session_id, report.cwd, report.part) == ("abc", "/work/shop-api", "statusline")
    assert report.spend.reported_usd == 1.2345 and report.spend.model == "claude-opus-4-6"
    assert report.transcript_path == "/tmp/abc.jsonl"
    assert budget.report_from("claude-code", {"session_id": "abc"}) is None


# --- Codex ---------------------------------------------------------------------

def _token_count(inp, cached, out, reasoning=0):
    return {"timestamp": "2026-10-12T10:00:00Z", "type": "event_msg", "payload": {
        "type": "token_count", "info": {
            "total_token_usage": {"input_tokens": inp, "cached_input_tokens": cached, "output_tokens": out,
                                  "reasoning_output_tokens": reasoning, "total_tokens": inp + out},
            "last_token_usage": {"input_tokens": 1, "cached_input_tokens": 0, "output_tokens": 1,
                                 "reasoning_output_tokens": 0, "total_tokens": 2},
            "model_context_window": 258400},
        "rate_limits": None}}


def test_codex_rollout_charges_cumulative_growth_to_the_model_in_use(tmp_path):
    """input_tokens includes the cached part; total_token_usage is cumulative."""
    path = _jsonl(tmp_path / "rollout-2026-10-12T10-00-00-thr.jsonl",
                  {"type": "session_meta", "payload": {"id": "thr", "cwd": "/work/shop-api"}},
                  {"type": "turn_context", "payload": {"model": "gpt-5-codex", "cwd": "/work/shop-api"}},
                  _token_count(1000, 400, 100, 30),
                  {"type": "event_msg", "payload": {"type": "token_count", "info": None}},
                  _token_count(3000, 1400, 300, 60),
                  {"type": "turn_context", "payload": {"model": "gpt-5-mini"}},
                  _token_count(4000, 2000, 400))

    spend = budget.usage_from_transcript("codex", path)

    big, mini = spend.tokens["gpt-5-codex"], spend.tokens["gpt-5-mini"]
    assert (big.input, big.cache_read, big.output) == (1600, 1400, 300)
    assert (mini.input, mini.cache_read, mini.output) == (400, 600, 100)
    usd, _ = budget.estimate(spend)
    assert usd == pytest.approx((1600 * 1.25 + 1400 * 0.125 + 300 * 10 + 400 * 0.25 + 600 * 0.025 + 100 * 2) / 1e6)


# --- Gemini CLI ----------------------------------------------------------------------

def test_gemini_session_jsonl_keeps_the_last_copy_of_each_message(tmp_path):
    tokens = lambda i, o, c=0, th=0, tool=0: {"input": i, "output": o, "cached": c, "thoughts": th,  # noqa: E731
                                               "tool": tool, "total": i + o + th + tool}
    path = _jsonl(tmp_path / "session-2026-10-12T10-00-abcd1234.jsonl",
                  {"sessionId": "abcd1234", "projectHash": "x", "startTime": "t", "lastUpdated": "t"},
                  {"id": "m1", "type": "user", "content": "hi"},
                  {"id": "m2", "type": "gemini", "model": "gemini-2.5-pro", "content": ""},
                  {"id": "m2", "type": "gemini", "model": "gemini-2.5-pro", "tokens": tokens(5000, 200, 3000, 50)},
                  {"id": "m3", "type": "gemini", "model": "gemini-2.5-flash", "tokens": tokens(1000, 100, tool=10)})

    spend = budget.usage_from_transcript("gemini", path)

    pro, flash = spend.tokens["gemini-2.5-pro"], spend.tokens["gemini-2.5-flash"]
    assert (pro.input, pro.cache_read, pro.output) == (2000, 3000, 250)
    assert (flash.input, flash.output) == (1010, 100)


def test_gemini_legacy_session_json(tmp_path):
    path = tmp_path / "session-old.json"
    path.write_text(json.dumps({"sessionId": "s", "messages": [
        {"id": "m1", "type": "gemini", "model": "gemini-2.5-flash",
         "tokens": {"input": 100, "output": 10, "cached": 0, "total": 110}}]}), encoding="utf-8")
    assert budget.usage_from_transcript("gemini", str(path)).total().input == 100


# --- OpenCode ------------------------------------------------------------------------

def _opencode(cost, completed=1760000000000, **tokens):
    return {"info": {"id": "msg_1", "sessionID": "ses_1", "role": "assistant", "modelID": "glm-4.6",
                     "providerID": "zai", "path": {"cwd": "/work/shop-api", "root": "/work/shop-api"},
                     "time": {"created": 1, "completed": completed}, "cost": cost,
                     "tokens": {"input": tokens.get("i", 1000), "output": tokens.get("o", 100), "reasoning": 20,
                                "cache": {"read": 500, "write": 0}}}}


def test_opencode_reports_its_own_cost_per_completed_message():
    report = budget.report_from("opencode", _opencode(0.0123))
    assert (report.session_id, report.part, report.cwd) == ("ses_1", "msg:msg_1", "/work/shop-api")
    assert report.spend.reported_usd == 0.0123
    assert report.spend.tokens["glm-4.6"].output == 120
    assert budget.report_from("opencode", _opencode(0.01, completed=None)) is None


def test_opencode_zero_cost_with_tokens_falls_back_to_the_price_table():
    report = budget.report_from("opencode", _opencode(0))
    assert report.spend.reported_usd is None
    usd, _ = budget.estimate(report.spend)
    assert usd == pytest.approx((1000 * 0.6 + 120 * 2.2 + 500 * 0.11) / 1e6)


# --- agents that expose no usage --------------------------------------------------------

@pytest.mark.parametrize("agent", ["cursor", "copilot", "grok", "windsurf", "kiro", "cline", "antigravity"])
def test_agents_without_documented_usage_are_never_guessed(agent, tmp_path):
    path = _jsonl(tmp_path / "t.jsonl", _claude_line("m", "claude-sonnet-4-5", 10, 10))
    assert budget.usage_from_transcript(agent, path) is None
    assert budget.report_from(agent, {"session_id": "x", "cost": {"total_cost_usd": 1}}) is None
    assert budget.source_of(agent)[0] == budget.UNKNOWN


def test_every_supported_agent_has_a_stated_spend_source():
    for key in AGENTS:
        kind, how = budget.source_of(key)
        assert kind in (budget.REPORTED, budget.ESTIMATE, budget.UNKNOWN) and how


def test_only_session_files_are_read(tmp_path):
    secret = tmp_path / "id_rsa"
    secret.write_text("x")
    assert budget.usage_from_transcript("claude-code", str(secret)) is None
    assert budget.usage_from_transcript("claude-code", str(tmp_path / "missing.jsonl")) is None


# --- prices ---------------------------------------------------------------------------

@pytest.mark.parametrize("model, expected", [
    ("claude-sonnet-4-5-20250929", (3.0, 15.0)),
    ("claude-opus-4-1-20250805", (15.0, 75.0)),
    ("claude-opus-4-6", (5.0, 25.0)),
    ("claude-haiku-4-5", (1.0, 5.0)),
    ("gpt-5-codex", (1.25, 10.0)),
    ("gpt-5.1-codex-max", (1.25, 10.0)),
    ("gpt-5-mini", (0.25, 2.0)),
    ("gemini-2.5-flash-lite", (0.1, 0.4)),
    ("gemini-2.5-pro", (1.25, 10.0)),
    ("zai/glm-4.6", (0.6, 2.2)),
    ("glm-4.5-air", (0.2, 1.1)),
    ("moonshotai/kimi-k2-instruct", (0.6, 2.5)),
    ("qwen3-coder-plus", (1.0, 5.0)),
])
def test_price_table_covers_common_models(model, expected):
    assert budget.price_for(model)[:2] == expected


def test_unknown_models_are_flagged_not_priced_at_zero():
    spend = budget.Spend()
    spend.add("my-local-llama", budget.Tokens(1000, 100))
    usd, unpriced = budget.estimate(spend)
    assert usd == 0 and unpriced == ["my-local-llama"]


def test_price_overrides_win_and_are_validated():
    overrides = budget.clean_prices({"Sonnet": {"input": 1, "output": 2}, "my-local-llama": {"input": 0.1}})
    assert budget.price_for("claude-sonnet-4-5", overrides) == (1.0, 2.0, 0.0, 0.0)
    assert budget.price_for("my-local-llama-3", overrides)[0] == 0.1
    with pytest.raises(ValueError):
        budget.clean_prices({"x": {"input": "lots"}})
    with pytest.raises(ValueError):
        budget.clean_prices({"x": {"input": -1}})
