"""Shared fixtures: an isolated db, git ledger repo and tracer for the coding gate."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, replace

import pytest

from sololicense.config import load_config
from sololicense.db.database import init_db
from sololicense.observability.neatlogs_client import init_neatlogs
from sololicense.observability.tracer import Tracer


@dataclass
class Harness:
    conn: object
    config: object
    tracer: Tracer
    repo: object


@pytest.fixture
def harness(tmp_path) -> Harness:
    repo = tmp_path / "repo"
    repo.mkdir()
    for args in (
        ["init", "-q"],
        ["config", "user.name", "Test"],
        ["config", "user.email", "test@example.com"],
    ):
        subprocess.run(["git", *args], cwd=repo, check=True)

    config = replace(
        load_config(),
        db_path=tmp_path / "test.db",
        neatlogs_api_key="",
        typesafe_api_key="",
        demo_mode=False,
        ledger_repo=repo,
        # A developer's .env may set a real key; tests that assert "saving a
        # secret is refused without one" need a clean slate regardless.
        settings_encryption_key="",
    )
    conn = init_db(config.db_path)
    return Harness(conn, config, Tracer(init_neatlogs(config)), repo)
