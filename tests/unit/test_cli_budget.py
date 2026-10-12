from sololicense import cli


def test_budget_lines_show_caps_sessions_and_a_stop():
    data = {
        "day": "2026-10-12",
        "repos": [{"repo": "shop-api", "day_usd": 1.7, "resumed_today": False,
                   "limits": {"session_usd": 1.0, "day_usd": 5.0, "warn_at": 0.8}}],
        "sessions": [{"usd": 1.24, "agent": "claude-code", "model": "claude-sonnet-4-5", "repo": "shop-api",
                      "source": "reported", "state": "cap", "blocked": True},
                     {"usd": 0.46, "agent": "codex", "model": "", "repo": "shop-api",
                      "source": "estimate", "state": "ok", "blocked": False}],
        "savings": {"usd_saved": 12.5},
    }
    text = "\n".join(cli.budget_lines(data))
    assert "shop-api: $1.70 of $5.00 today (34%) | per session $1.00" in text
    assert "$1.24  claude-code (claude-sonnet-4-5) in shop-api | reported by the agent | STOPPED at the cap" in text
    assert "$0.46  codex in shop-api | estimated from tokens | ok" in text
    assert "Developer time saved by earned autonomy: $12.50" in text
    assert "press Resume" in text


def test_budget_without_caps_or_repos():
    assert "no repositories yet" in "\n".join(cli.budget_lines({"repos": [], "sessions": []}))
    lines = cli.budget_lines({"repos": [{"repo": "r", "day_usd": 0.2, "limits": {}}], "sessions": []})
    assert "r: $0.20 of no cap today | per session no cap" in lines[1]


def test_budget_command_says_when_the_gate_is_down(capsys, monkeypatch):
    monkeypatch.setattr(cli, "_get", lambda url, timeout=3.0: None)
    assert cli.main(["budget", "--url", "http://127.0.0.1:9"]) == 1
    assert "not answering" in capsys.readouterr().out
