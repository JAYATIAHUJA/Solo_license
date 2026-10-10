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
