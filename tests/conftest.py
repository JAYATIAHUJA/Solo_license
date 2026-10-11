"""Shared fixtures: a fully wired worker over an isolated db and git repo."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, replace

import pytest

from sololicense.agent.planner import Planner
from sololicense.agent.worker import RefundWorker
from sololicense.config import load_config
from sololicense.db.database import init_db
from sololicense.db.seed import seed
from sololicense.faults.injector import FaultInjector
from sololicense.observability.neatlogs_client import init_neatlogs
from sololicense.observability.tracer import Tracer
from sololicense.services.git_ledger import GitLedger
from sololicense.services import economics
from sololicense.services.license_service import LicenseService
from sololicense.services.policy_service import PolicyService


@dataclass
class Harness:
    conn: object
    config: object
    worker: RefundWorker
    license_service: LicenseService
    fault_injector: FaultInjector
    repo: object
    agent: object = None


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
        llm_provider="deterministic",
        neatlogs_api_key="",
        demo_mode=False,
        alert_webhook_url="",
        ledger_repo=repo,
        # A developer's .env may set a real key; tests that assert "saving a
        # secret is refused without one" need a clean slate regardless.
        settings_encryption_key="",
    )
    conn = init_db(config.db_path)
    seed(conn, config)

    tracer = Tracer(init_neatlogs(config))
    license_service = LicenseService(
        conn, GitLedger(repo_root=repo),
        ladder=economics.trust_ladder({}, config.trust_confidence),
    )
    policy_service = PolicyService(conn, config)
    policy_service.ensure_default_policy()
    faults = FaultInjector(conn)
    worker = RefundWorker(
        conn, config, tracer=tracer, license_service=license_service,
        policy_service=policy_service,
        fault_injector=faults, planner=Planner(config),
    )
    from sololicense.agent.loop import TicketAgent

    agent = TicketAgent(conn, config, tracer=tracer, worker=worker)
    return Harness(conn, config, worker, license_service, faults, repo, agent)
