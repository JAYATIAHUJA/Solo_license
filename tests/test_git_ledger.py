import subprocess

from sololicense.services.git_ledger import GitLedger, LedgerEntry


def test_git_ledger_initializes_configured_repo_on_first_record(tmp_path):
    repo = tmp_path / "ledger-repo"
    ledger = GitLedger(repo_root=repo)

    sha = ledger.record(
        LedgerEntry(
            task_class="refund",
            kind="restore",
            from_level=0,
            to_level=2,
            reason="evidence reviewed",
            run_id=7,
            trace_id="trace-1",
        )
    )

    assert sha
    assert (repo / "ledger" / "license_ledger.jsonl").exists()
    log = subprocess.run(
        ["git", "log", "--oneline"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert "license(refund): restore L0 -> L2" in log


def test_ledger_commit_never_includes_other_staged_work(tmp_path):
    repo = tmp_path / "project"
    repo.mkdir()
    for args in (["init", "-q"], ["config", "user.name", "Dev"], ["config", "user.email", "d@x.io"]):
        subprocess.run(["git", *args], cwd=repo, check=True)
    (repo / "README.md").write_text("hi")
    subprocess.run(["git", "add", "README.md"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=repo, check=True)
    (repo / "feature.py").write_text("print(1)")
    subprocess.run(["git", "add", "feature.py"], cwd=repo, check=True)  # someone's staged work

    sha = GitLedger(repo_root=repo).record(
        LedgerEntry("refund", "demote", 2, 0, "state mismatch", 3, "t")
    )

    files = subprocess.run(
        ["git", "show", "--name-only", "--format=", sha], cwd=repo,
        capture_output=True, text=True, check=True,
    ).stdout.split()
    staged = subprocess.run(
        ["git", "diff", "--cached", "--name-only"], cwd=repo,
        capture_output=True, text=True, check=True,
    ).stdout.split()
    assert files == ["ledger/license_ledger.jsonl"]
    assert staged == ["feature.py"]
