"""Composition root.

The one place where concrete dependencies are constructed and wired. Both the
Streamlit UI and the command-line scripts build their world through
:func:`build_app`, so there is a single, consistent assembly order — and
neatlogs is initialised here, before any agent object exists, as required."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from sololicense.agent.planner import Planner
from sololicense.agent.worker import RefundWorker
from sololicense.config import Config, load_config, with_overrides
from sololicense.db.repositories import settings as settings_repo
from sololicense.db.database import init_db
from sololicense.faults.injector import FaultInjector
from sololicense.observability.neatlogs_client import NeatlogsClient, init_neatlogs
from sololicense.observability.tracer import Tracer
from sololicense.services.git_ledger import GitLedger
from sololicense.services.license_service import LicenseService


@dataclass
class AppContext:
    """Fully wired application, ready to serve a UI or a script."""

    config: Config
    conn: sqlite3.Connection
    neatlogs: NeatlogsClient
    worker: RefundWorker
    license_service: LicenseService
    fault_injector: FaultInjector


def build_app(
    config: Config | None = None, *, check_same_thread: bool = True
) -> AppContext:
    config = config or load_config()

    # 1. Persistence first, so operator settings can override the environment.
    conn = init_db(config.db_path, check_same_thread=check_same_thread)
    config = with_overrides(config, settings_repo.get_all(conn))

    # 2. Observability — instrument before any agent logic.
    neatlogs = init_neatlogs(config)
    tracer = Tracer(neatlogs)

    # 3. Services and the agent.
    license_service = LicenseService(
        conn, GitLedger(repo_root=config.ledger_repo),
        promotion_threshold=config.promotion_clean_runs,
    )
    fault_injector = FaultInjector(conn)
    planner = Planner(config)
    worker = RefundWorker(
        conn,
        config,
        tracer=tracer,
        license_service=license_service,
        fault_injector=fault_injector,
        planner=planner,
    )

    return AppContext(
        config=config,
        conn=conn,
        neatlogs=neatlogs,
        worker=worker,
        license_service=license_service,
        fault_injector=fault_injector,
    )
