from pathlib import Path

from sololicense.config import load_config
from sololicense.domain.models import RunStatus


def test_load_config_reads_ledger_repo(monkeypatch, tmp_path):
    ledger_repo = tmp_path / "ledger-repo"
    monkeypatch.setenv("SOLO_LEDGER_REPO", str(ledger_repo))

    config = load_config()

    assert config.ledger_repo == ledger_repo


def test_approved_status_is_a_run_status_value():
    assert RunStatus.APPROVED.value == "approved"
