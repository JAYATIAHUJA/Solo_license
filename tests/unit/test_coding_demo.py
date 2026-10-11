"""The demo kit: the demo repo sets up cleanly and the report reads right."""

from __future__ import annotations

import json
import subprocess

from scripts import coding_demo


def test_setup_makes_a_git_repo_with_the_hooks(tmp_path):
    repo = coding_demo.setup(tmp_path / "shop")
    assert (repo / "cart.js").exists() and (repo / ".git").exists()
    hooks = json.loads((repo / ".claude" / "settings.local.json").read_text())
    assert "PermissionRequest" in hooks["hooks"]
    log = subprocess.run(["git", "log", "--oneline"], cwd=repo, capture_output=True, text=True).stdout
    assert log.strip()


def test_the_demo_repo_has_the_two_bugs_the_story_needs(tmp_path):
    repo = coding_demo.setup(tmp_path / "shop")
    result = subprocess.run("npm test --silent", cwd=repo, shell=True, capture_output=True, text=True, timeout=120)
    out = result.stdout + result.stderr
    assert result.returncode != 0
    assert "total multiplies price by quantity" in out and "the 10th item is already discounted" in out


def test_report_shows_before_and_after():
    result = {
        "before": {"prompts": 21, "over_edit_lines_reviewed": 157, "forbidden_prompts": 3, "failed_turns_unnoticed": 0},
        "after": {"prompts": 11, "auto_allowed": 19, "denied": 3, "over_edits_sent_back": 1,
                  "over_edit_lines_reviewed": 0, "turns_failed_checks": 0},
        "days": [{"day": 1, "prompts": 9, "auto_allowed": 1}],
        "turns": [{"day": 1, "prompt": "Fix it", "sent_back": "", "status": "verified", "scope_score": 5,
                   "lines_changed": 2, "tests": "passed"}],
        "licenses": [{"action_class": "test-run", "level": 2, "successes": 14, "failures": 0}],
        "events": [{"task_class": "test-run@shop-api", "kind": "promote", "from_level": 0, "to_level": 1}],
        "traces": ["t"], "neatlogs": False,
    }
    text = coding_demo.report(result)
    assert "| Permission prompts you answer | 21 | **11** |" in text
    assert "**3 denied**" in text and "`test-run` | L2" in text
