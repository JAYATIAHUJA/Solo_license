"""One composer: the same remediation for every agent, in plain words plus commands."""

from __future__ import annotations

from sololicense.coding.remediation import compose


def test_a_failed_install_says_what_to_undo():
    r = compose("tool-failed", action_class="install-dep", command="npm install left-pad",
                reason="Exit code 1", demoted=True)
    assert r.revert_commands == ("git checkout -- package.json package-lock.json",)
    assert r.text.startswith("Solo License: `npm install left-pad` failed and install-dep is back to asking.")
    assert "Undo the partial change (`git checkout -- package.json package-lock.json`)" in r.text
    assert r.text.endswith("continue without it.")


def test_each_package_manager_reverts_its_own_manifest():
    assert compose("tool-failed", action_class="install-dep", command="pnpm add zod").revert_commands == \
        ("git checkout -- package.json pnpm-lock.yaml",)
    assert compose("tool-failed", action_class="install-dep", command="cargo add serde").revert_commands == \
        ("git checkout -- Cargo.toml Cargo.lock",)
    assert compose("tool-failed", action_class="install-dep", command="uv add httpx").revert_commands == \
        ("git checkout -- pyproject.toml uv.lock",)


def test_a_class_that_was_already_asking_is_not_said_to_drop():
    r = compose("tool-failed", action_class="install-dep", command="npm i x", demoted=False)
    assert "install-dep still asks." in r.text


def test_an_edit_failure_reverts_the_file():
    r = compose("tool-failed", action_class="file-edit", command="Edit src/app.py", files=("src/app.py",))
    assert r.revert_commands == ("git checkout -- src/app.py",)


def test_without_a_known_revert_the_agent_is_told_to_check_git_status():
    r = compose("tool-failed", action_class="git-remote", command="git push origin main")
    assert r.revert_commands == ()
    assert "`git status`" in r.text


def test_a_failed_turn_names_files_stash_and_the_entire_checkpoint():
    r = compose("turn-failed", reason="the tests fail after this turn's changes.",
                files=("src/a.py", "src/b.py"), base_ref="0123456789abcdef", checkpoint="cp_abcdef123456789",
                classes=("file-edit",))
    assert r.text.startswith("Solo License: the tests fail after this turn's changes.")
    assert "This turn changed: src/a.py, src/b.py." in r.text
    assert "`git checkout 0123456789ab -- <file>`" in r.text
    assert r.revert_commands == ("git stash push --include-untracked -m \"solo-license: undo turn\"",)
    assert r.revert_commands[0] in r.text
    assert "entire checkpoint explain cp_abcdef123" in r.text
    assert "file-edit is back to asking" in r.text


def test_a_flag_tells_the_agent_to_revert_before_continuing():
    r = compose("flagged", reason="it deleted the migration", files=("db/001.sql",), classes=("file-edit",))
    assert r.text.startswith("Solo License: Your last turn was flagged by the user: it deleted the migration.")
    assert "before continuing" in r.text and "db/001.sql" in r.text and "git stash push" in r.text


def test_a_flagged_decision_names_its_command_and_revert():
    r = compose("flagged", reason="not this package", action_class="install-dep", command="npm install left-pad",
                classes=("install-dep",))
    assert "Revert what `npm install left-pad` changed (`git checkout -- package.json package-lock.json`)" in r.text
    assert "install-dep is back to asking" in r.text


def test_repeated_denials_tell_the_agent_to_stop():
    r = compose("denied", reason="Blocked: force-pushes are never allowed.", attempts=3)
    assert "3 blocked attempts this turn" in r.text and "ask the user" in r.text
