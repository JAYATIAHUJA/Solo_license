"""End-of-turn checks: over-editing is sent back, failing tests demote, a clean turn is evidence."""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

from sololicense.coding import verify
from sololicense.coding.gate import CodingGate
from sololicense.coding.jev import JevClient
from sololicense.db.repositories import agent as agent_repo
from sololicense.services.git_ledger import GitLedger

PRICE = "def total(items):\n    return sum(i['price'] for i in items)\n"


def _project(path):
    path.mkdir()
    for args in (["init", "-q"], ["config", "user.name", "T"], ["config", "user.email", "t@example.com"]):
        subprocess.run(["git", *args], cwd=path, check=True)
    (path / "cart.py").write_text(PRICE)
    (path / "util.py").write_text("\n".join(f"X{i} = {i}" for i in range(40)) + "\n")
    subprocess.run(["git", "add", "."], cwd=path, check=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=path, check=True)
    return path


@pytest.fixture
def gate(harness, tmp_path):
    project = _project(tmp_path / "shop")
    gate = CodingGate(harness.conn, harness.tracer, GitLedger(repo_root=harness.repo),
                      jev_client=JevClient(), verifier=verify.check_turn,
                      checkpoint_lookup=lambda cwd, session: None)
    gate.project = project
    return gate


def _ev(gate, **f):
    return {"session_id": "s", "cwd": str(gate.project), **f}


def test_small_focused_fix_passes(gate):
    gate.user_prompt(_ev(gate, prompt="fix the bug in cart.py: total should include quantity"))
    (gate.project / "cart.py").write_text(PRICE.replace("i['price']", "i['price'] * i['qty']"))
    assert gate.stop(_ev(gate)) == {}
    turn = agent_repo.current_turn(gate.conn, "s")
    assert turn["status"] == "verified" and turn["scope_score"] == 5


def test_over_editing_is_sent_back_with_the_unrelated_files(gate):
    gate.user_prompt(_ev(gate, prompt="fix the bug in cart.py: total should include quantity"))
    (gate.project / "cart.py").write_text(PRICE.replace("i['price']", "i['price'] * i['qty']"))
    (gate.project / "util.py").write_text("\n".join(f"CONSTANT_{i} = {i * 2}" for i in range(60)) + "\n")
    (gate.project / "helpers.py").write_text("\n".join(f"def h{i}(): return {i}" for i in range(30)) + "\n")

    answer = gate.stop(_ev(gate))
    assert answer["decision"] == "block"
    assert "over-editing" in answer["reason"] and "util.py" in answer["reason"]
    assert "cart.py" not in answer["reason"].split("edits in:")[1]
    assert agent_repo.get_license(gate.conn, "shop", "file-edit")["failures"] == 1


def test_failing_tests_after_the_change_block_the_turn(gate):
    # A check that passes now and fails only with the agent's change: a regression.
    (gate.project / "check_broken.py").write_text("import sys; sys.exit('BROKEN' in open('cart.py').read())\n")
    subprocess.run(["git", "add", "."], cwd=gate.project, check=True)
    subprocess.run(["git", "commit", "-qm", "check"], cwd=gate.project, check=True)
    agent_repo.ensure_repo(gate.conn, "shop", str(gate.project))
    agent_repo.set_test_command(gate.conn, "shop", f'"{sys.executable}" check_broken.py')

    gate.user_prompt(_ev(gate, prompt="refactor the cart module"))
    (gate.project / "cart.py").write_text(PRICE + "\nBROKEN = True\n")
    answer = gate.stop(_ev(gate))
    assert answer["decision"] == "block" and "tests fail" in answer["reason"]


def test_passing_tests_verify_the_turn(gate):
    gate.user_prompt(_ev(gate, prompt="refactor the cart module"))
    (gate.project / "cart.py").write_text(PRICE + "\n# tidy\n")
    agent_repo.ensure_repo(gate.conn, "shop", str(gate.project))
    agent_repo.set_test_command(gate.conn, "shop", f'"{sys.executable}" -c "pass"')
    assert gate.stop(_ev(gate)) == {}
    assert agent_repo.current_turn(gate.conn, "s")["tests"] == "passed"


def test_no_changes_means_nothing_to_check(gate):
    gate.user_prompt(_ev(gate, prompt="explain cart.py"))
    assert gate.stop(_ev(gate)) == {}


def test_detects_npm_and_pytest_commands(tmp_path):
    (tmp_path / "package.json").write_text(json.dumps({"scripts": {"test": "vitest run"}}))
    assert verify.detect_test_command(str(tmp_path)) == "npm test --silent"
    (tmp_path / "package.json").write_text(json.dumps({"scripts": {"test": 'echo "Error: no test specified"'}}))
    assert verify.detect_test_command(str(tmp_path)) is None
    (tmp_path / "pytest.ini").write_text("[pytest]\n")
    assert verify.detect_test_command(str(tmp_path)).endswith("pytest -q -x")


def test_tooling_files_and_old_untracked_files_are_not_the_agents_changes(gate):
    import os
    import time

    (gate.project / ".claude").mkdir()
    (gate.project / ".claude" / "settings.local.json").write_text("{}")
    old = gate.project / "notes.txt"
    old.write_text("draft\n")
    past = time.time() - 3600
    os.utime(old, (past, past))
    gate.user_prompt(_ev(gate, prompt="explain cart.py"))
    assert gate.stop(_ev(gate)) == {}
    assert agent_repo.current_turn(gate.conn, "s")["files_changed"] == 0


def test_a_failed_turn_points_at_the_entire_checkpoint_and_can_be_rewound(gate):
    from sololicense.coding import entire

    gate.checkpoint_lookup = lambda cwd, session: {"checkpoint_id": "abc123def4567890", "date": "x"}
    gate.user_prompt(_ev(gate, prompt="fix the bug in cart.py"))
    (gate.project / "cart.py").write_text(PRICE.replace("i['price']", "i['price'] * i['qty']"))
    (gate.project / "util.py").write_text("\n".join(f"CONSTANT_{i} = {i * 2}" for i in range(80)) + "\n")
    gate.stop(_ev(gate))

    turn = agent_repo.current_turn(gate.conn, "s")
    assert turn["entire_checkpoint"] == "abc123def4567890"
    event = gate.conn.execute("SELECT reason FROM agent_events ORDER BY id DESC LIMIT 1").fetchone()
    assert event is None or "entire checkpoint explain abc123def456" in event["reason"]

    result = entire.rewind(str(gate.project), turn["base_ref"], "solo-license: rewind turn 1")
    assert result["ok"]
    assert (gate.project / "cart.py").read_text() == PRICE
    stashes = subprocess.run(["git", "stash", "list"], cwd=gate.project, capture_output=True, text=True).stdout
    assert "solo-license: rewind turn 1" in stashes


def test_tests_that_were_already_failing_are_not_held_against_the_agent(gate):
    (gate.project / "check.py").write_text("import sys; print('not ok 1 - always broken'); sys.exit(1)\n")
    subprocess.run(["git", "add", "."], cwd=gate.project, check=True)
    subprocess.run(["git", "commit", "-qm", "broken test"], cwd=gate.project, check=True)
    agent_repo.ensure_repo(gate.conn, "shop", str(gate.project))
    agent_repo.set_test_command(gate.conn, "shop", f'"{sys.executable}" check.py')

    gate.user_prompt(_ev(gate, prompt="fix the bug in cart.py"))
    (gate.project / "cart.py").write_text(PRICE.replace("i['price']", "i['price'] * i['qty']"))
    assert gate.stop(_ev(gate)) == {}
    turn = agent_repo.current_turn(gate.conn, "s")
    assert turn["status"] == "verified" and turn["tests"] == "failing before and after"


def test_a_regression_after_passing_tests_is_blamed(gate):
    (gate.project / "check.py").write_text("import cart, sys; sys.exit(0 if 'qty' not in open('cart.py').read() else 1)\n")
    subprocess.run(["git", "add", "."], cwd=gate.project, check=True)
    subprocess.run(["git", "commit", "-qm", "test"], cwd=gate.project, check=True)
    agent_repo.ensure_repo(gate.conn, "shop", str(gate.project))
    agent_repo.set_test_command(gate.conn, "shop", f'"{sys.executable}" check.py')

    gate.user_prompt(_ev(gate, prompt="fix the bug in cart.py"))
    (gate.project / "cart.py").write_text(PRICE.replace("i['price']", "i['price'] * i['qty']"))
    assert gate.stop(_ev(gate))["decision"] == "block"


def test_a_regression_is_still_blamed_when_tests_need_untracked_dependencies(gate):
    """The baseline worktree borrows node_modules/.venv; without them every
    baseline run would fail and hide real regressions (trail #25 finding)."""
    deps = gate.project / "node_modules"
    deps.mkdir()
    (deps / "helper.py").write_text("OK = True\n")
    (gate.project / ".gitignore").write_text("node_modules/\n")
    (gate.project / "check_dep.py").write_text(
        "import sys; sys.path.insert(0, 'node_modules'); import helper\n"
        "sys.exit('BROKEN' in open('cart.py').read())\n"
    )
    subprocess.run(["git", "add", "."], cwd=gate.project, check=True)
    subprocess.run(["git", "commit", "-qm", "check with a dependency"], cwd=gate.project, check=True)
    agent_repo.ensure_repo(gate.conn, "shop", str(gate.project))
    agent_repo.set_test_command(gate.conn, "shop", f'"{sys.executable}" check_dep.py')

    gate.user_prompt(_ev(gate, prompt="refactor the cart module"))
    (gate.project / "cart.py").write_text(PRICE + "\nBROKEN = True\n")
    answer = gate.stop(_ev(gate))
    assert answer["decision"] == "block" and "tests fail" in answer["reason"]
    # The borrowed dependencies are untouched by the cleanup.
    assert (deps / "helper.py").read_text() == "OK = True\n"


def test_unknown_baseline_counts_as_the_agents_failure(gate, monkeypatch):
    monkeypatch.setattr(verify, "tests_before", lambda root, base, command: None)
    (gate.project / "check_broken.py").write_text("import sys; sys.exit('BROKEN' in open('cart.py').read())\n")
    subprocess.run(["git", "add", "."], cwd=gate.project, check=True)
    subprocess.run(["git", "commit", "-qm", "check"], cwd=gate.project, check=True)
    agent_repo.ensure_repo(gate.conn, "shop", str(gate.project))
    agent_repo.set_test_command(gate.conn, "shop", f'"{sys.executable}" check_broken.py')
    gate.user_prompt(_ev(gate, prompt="refactor the cart module"))
    (gate.project / "cart.py").write_text(PRICE + "\nBROKEN = True\n")
    assert gate.stop(_ev(gate))["decision"] == "block"


def _tap(*failing):
    return "".join(f"not ok {i} - {name}\n" for i, name in enumerate(failing, 1))


def test_failing_tests_are_compared_test_by_test():
    assert verify.failing_tests("FAILED tests/a.py::test_x - boom\n") == {"tests/a.py::test_x"}
    assert verify.failing_tests(_tap("cart total")) == {"cart total"}
    assert verify.failing_tests("--- FAIL: TestCart (0.00s)\n") == {"TestCart"}
    assert verify.failing_tests("  ✕ adds tax (3 ms)\n") == {"adds tax"}
    assert verify.failing_tests("some unreadable output") is None


def test_fixing_an_old_failure_while_adding_a_new_one_is_a_regression(monkeypatch):
    """Trail #25 finding: a stale 'already failing' verdict must not hide a new failure."""
    monkeypatch.setattr(verify, "tests_before", lambda r, b, c: (False, _tap("old discount bug")))
    regression, why = verify.is_regression(".", "base", "npm test", _tap("new cart bug"))
    assert regression and "new cart bug" in why

    regression, _ = verify.is_regression(".", "base", "npm test", _tap("old discount bug"))
    assert not regression

    monkeypatch.setattr(verify, "tests_before", lambda r, b, c: (False, "garbled"))
    assert verify.is_regression(".", "base", "npm test", _tap("x"))[0]


def test_every_turn_compares_against_its_own_starting_point(gate):
    """Turn 1 leaves an old failure; turn 2 fixes it and breaks something else."""
    check = gate.project / "check.py"
    check.write_text(
        "import sys\n"
        "src = open('cart.py').read()\n"
        "bad = []\n"
        "if 'OLD' in src: bad.append('old')\n"
        "if 'NEW' in src: bad.append('new')\n"
        "for i, b in enumerate(bad, 1): print(f'not ok {i} - {b}')\n"
        "sys.exit(1 if bad else 0)\n"
    )
    (gate.project / "cart.py").write_text(PRICE + "OLD = 1\n")
    subprocess.run(["git", "add", "."], cwd=gate.project, check=True)
    subprocess.run(["git", "commit", "-qm", "old failure"], cwd=gate.project, check=True)
    agent_repo.ensure_repo(gate.conn, "shop", str(gate.project))
    agent_repo.set_test_command(gate.conn, "shop", f'"{sys.executable}" check.py')

    gate.user_prompt(_ev(gate, prompt="refactor the cart module"))
    (gate.project / "cart.py").write_text(PRICE + "OLD = 1\n# tidy\n")
    assert gate.stop(_ev(gate)) == {}                     # old failure only: not the agent's

    subprocess.run(["git", "commit", "-qam", "turn 1"], cwd=gate.project, check=True)
    gate.user_prompt(_ev(gate, prompt="refactor the cart module"))
    (gate.project / "cart.py").write_text(PRICE + "NEW = 1\n")
    answer = gate.stop(_ev(gate))
    assert answer["decision"] == "block" and "newly failing: new" in answer["reason"]
