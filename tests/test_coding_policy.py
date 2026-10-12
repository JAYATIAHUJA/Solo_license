"""Coding policy: the team's file and this machine's settings only ever tighten."""

from __future__ import annotations

import subprocess

import pytest

from sololicense.coding import policy
from sololicense.coding.gate import CodingGate
from sololicense.coding.jev import JevClient
from sololicense.db.repositories import agent as agent_repo
from sololicense.services.git_ledger import GitLedger


@pytest.fixture
def gate(harness, tmp_path):
    project = tmp_path / "shop-api"
    project.mkdir()
    for args in (["init", "-q"], ["config", "user.name", "T"], ["config", "user.email", "t@example.com"]):
        subprocess.run(["git", *args], cwd=project, check=True)
    (project / "app.py").write_text("x = 1\n")
    subprocess.run(["git", "add", "."], cwd=project, check=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=project, check=True)
    g = CodingGate(harness.conn, harness.tracer, GitLedger(repo_root=harness.repo),
                   jev_client=JevClient(), checkpoint_lookup=lambda cwd, session: None)
    g.project = project
    return g


def _bash(gate, command):
    return {"session_id": "s", "cwd": str(gate.project), "tool_name": "Bash", "tool_input": {"command": command}}


def _edit(gate, path):
    return {"session_id": "s", "cwd": str(gate.project), "tool_name": "Edit",
            "tool_input": {"file_path": str(gate.project / path)}}


def _decision(answer):
    return (answer.get("hookSpecificOutput") or {}).get("decision", {}).get("behavior", "defer")


def _earn(gate, key, level):
    agent_repo.get_license(gate.conn, "shop-api", key)
    agent_repo.set_level(gate.conn, "shop-api", key, level)


def _write_file_policy(gate, text):
    path = gate.project / ".solo-license" / "policy.toml"
    path.parent.mkdir(exist_ok=True)
    path.write_text(text)


def test_without_any_policy_the_built_in_rules_apply(gate):
    gate.user_prompt({"session_id": "s", "cwd": str(gate.project), "prompt": "x"})
    _earn(gate, "test-run", 2)
    assert _decision(gate.permission(_bash(gate, "npm test"))) == "allow"


def test_the_repo_file_caps_a_class_even_after_it_was_earned(gate):
    gate.user_prompt({"session_id": "s", "cwd": str(gate.project), "prompt": "x"})
    _earn(gate, "test-run", 2)
    _write_file_policy(gate, "[classes]\ntest-run = { max = 0 }\n")
    answer = gate.permission(_bash(gate, "npm test"))
    assert _decision(answer) == "defer" and "always asks in this repo" in answer["systemMessage"]


def test_deny_rules_from_the_file_block_commands_and_paths(gate):
    gate.user_prompt({"session_id": "s", "cwd": str(gate.project), "prompt": "x"})
    _earn(gate, "file-edit", 2)
    _write_file_policy(gate, '[deny]\ncommands = ["terraform destroy"]\npaths = [".env", "infra/prod/**"]\n')
    assert _decision(gate.permission(_edit(gate, "app.py"))) == "allow"
    assert _decision(gate.permission(_bash(gate, "terraform destroy -auto-approve"))) == "deny"
    assert _decision(gate.permission(_edit(gate, "infra/prod/main.tf"))) == "deny"
    assert _decision(gate.permission(_edit(gate, ".env"))) == "deny"
    # Reaching for a forbidden file is a failure: the class is back to asking.
    assert agent_repo.get_license(gate.conn, "shop-api", "file-edit")["level"] == 0
    assert _decision(gate.permission(_edit(gate, "app.py"))) == "defer"


def test_freeze_makes_everything_ask(gate):
    gate.user_prompt({"session_id": "s", "cwd": str(gate.project), "prompt": "x"})
    _earn(gate, "test-run", 2)
    policy.save_local(gate.conn, policy.ALL_REPOS, {"freeze": {"enabled": True}})
    answer = gate.permission(_bash(gate, "npm test"))
    assert _decision(answer) == "defer" and "Frozen" in answer["systemMessage"]


def test_local_settings_cannot_loosen_the_team_file(gate):
    _write_file_policy(gate, "[classes]\ninstall-dep = { max = 0 }\n")
    policy.save_local(gate.conn, "shop-api", {"classes": {"install-dep": {"max": 2}}})
    rules = policy.effective(gate.conn, "shop-api", gate.project)
    assert rules.ceilings["install-dep"] == 0


def test_policies_never_raise_a_built_in_ceiling(gate):
    policy.save_local(gate.conn, "shop-api", {"classes": {"git-remote": {"max": 2}}})
    assert policy.effective(gate.conn, "shop-api", gate.project).ceilings["git-remote"] == 1


def test_promotion_stops_at_the_policy_ceiling(gate):
    gate.user_prompt({"session_id": "s", "cwd": str(gate.project), "prompt": "x"})
    _write_file_policy(gate, "[classes]\ntest-run = { max = 1 }\n")
    for _ in range(20):
        gate.permission(_bash(gate, "npm test"))
        gate.tool_result(_bash(gate, "npm test"), failed=False)
    assert agent_repo.get_license(gate.conn, "shop-api", "test-run")["level"] == 1


def test_a_broken_policy_file_freezes_instead_of_loosening(gate):
    _write_file_policy(gate, "[classes\nthis is not toml")
    rules = policy.effective(gate.conn, "shop-api", gate.project)
    assert rules.freeze and all(level == 0 for level in rules.ceilings.values())
    _write_file_policy(gate, "[classes]\nnot-a-class = { max = 1 }\n")
    assert policy.effective(gate.conn, "shop-api", gate.project).freeze


def test_policy_api_saves_records_and_freezes(gate, harness, tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from sololicense.api import app as app_module
    from sololicense.db.database import init_db
    from sololicense.security import Actor, Role

    conn = init_db(tmp_path / "policy.db", check_same_thread=False)
    threaded = CodingGate(conn, harness.tracer, GitLedger(repo_root=harness.repo),
                          jev_client=JevClient(), checkpoint_lookup=lambda cwd, session: None)
    agent_repo.ensure_repo(conn, "shop-api", str(gate.project))
    conn.commit()

    class Ctx:
        coding_gate = threaded

    Ctx.conn = conn
    monkeypatch.setattr(app_module, "get_context", lambda: Ctx)
    app_module.app.dependency_overrides[app_module.current_actor] = lambda: Actor(actor_id="human:jayati", role=Role.ADMIN)
    try:
        client = TestClient(app_module.app)
        body = client.put("/api/coding/policy", json={"repo": "shop-api", "classes": {"install-dep": 1},
                                                       "deny_paths": [".env"]}).json()
        assert body["effective"]["ceilings"]["install-dep"] == 1 and ".env" in body["effective"]["deny_paths"]
        assert client.put("/api/coding/policy", json={"repo": "shop-api", "classes": {"nope": 1}}).status_code == 422
        frozen = client.post("/api/coding/freeze", json={"repo": "*", "enabled": True}).json()
        assert all(r["frozen"] for r in frozen["repos"])
        events = [r["reason"] for r in conn.execute("SELECT reason FROM agent_events WHERE kind = 'policy'")]
        assert any("freeze on" in e for e in events) and any("install-dep<=L1" in e for e in events)
        log = subprocess.run(["git", "log", "--format=%s"], cwd=harness.repo, capture_output=True, text=True).stdout
        assert "policy(policy@*): freeze on for all repositories" in log
    finally:
        app_module.app.dependency_overrides.clear()


def test_policy_init_writes_a_starter_that_parses(tmp_path):
    path = policy.write_starter(tmp_path)
    rules = policy.from_file(tmp_path)
    assert path.exists() and not rules.freeze and ".env" in rules.deny_paths


def test_a_policy_denial_demotes_the_class_like_a_hard_deny(gate):
    """Trail #31: a command the repo's policy forbids is a failure - the class
    drops to L0 and the attempt is recorded - so it cannot simply be retried."""
    gate.user_prompt({"session_id": "s", "cwd": str(gate.project), "prompt": "x"})
    _earn(gate, "install-dep", 2)
    _write_file_policy(gate, '[deny]\ncommands = ["npm install left-pad"]\n')
    assert _decision(gate.permission(_bash(gate, "npm install left-pad"))) == "deny"
    lic = agent_repo.get_license(gate.conn, "shop-api", "install-dep")
    assert lic["level"] == 0 and lic["demoted_from"] == 2 and lic["failures"] == 1
    assert _decision(gate.permission(_bash(gate, "npm install lodash"))) == "defer"
    by = gate.conn.execute("SELECT decided_by FROM agent_decisions WHERE command = 'npm install left-pad'").fetchone()
    assert by["decided_by"] == "policy"


@pytest.mark.parametrize("target", ["../other-repo/.env", "../../x/infra/prod/main.tf", "sub/../.env", "/etc/app/.env"])
def test_path_traversal_cannot_dodge_a_deny_rule(gate, target):
    """Trail #31: paths outside the repo (or with ..) are normalised and still matched."""
    rules = policy.Policy(deny_paths=(".env", "infra/prod/**"))
    assert policy.denied(rules, "Edit", {"file_path": target}, gate.project)


def test_unrelated_paths_outside_the_repo_are_not_denied(gate):
    rules = policy.Policy(deny_paths=(".env",))
    assert not policy.denied(rules, "Edit", {"file_path": "../notes/todo.md"}, gate.project)


@pytest.mark.parametrize("command, denied", [
    ("cat .env", True),
    ("cp ../secrets/.env /tmp/x", True),
    ("terraform apply infra/prod/main.tf", True),
    ("echo hi > .env", True),
    ("echo hi>.env", True),                     # Trail #31: glued to a redirection
    ("cat .env|less", True),
    ("cat<.env", True),
    ("(cat .env)", True),
    ("true;cat .env", True),
    ("x=$(cat .env)", True),
    ("echo `cat .env`", True),
    ("cat '.env'", True),
    ("FILE=.env ./run.sh", True),
    ("cat --file=.env", True),                  # Trail #32: paths inside options
    ("terraform apply -var-file=infra/prod/secrets.tfvars", True),
    ("curl --output=.env http://example.com/x", True),
    ("curl -o.env http://example.com/x", True),
    ("npm test --watch=false", False),
    ("git commit -m fix -v", False),
    ("cd deployment && npm test", False),       # contains 'env', not the file .env
    ("npm run env:check", False),
    ("ls environments/", False),
])
def test_paths_in_commands_are_matched_as_paths_not_substrings(gate, command, denied):
    rules = policy.Policy(deny_paths=(".env", "infra/prod/**"))
    assert bool(policy.denied(rules, "Bash", {"command": command}, gate.project)) is denied
