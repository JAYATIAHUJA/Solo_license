"""Composition root.

The one place where concrete dependencies are constructed and wired. Both the
Streamlit UI and the command-line scripts build their world through
:func:`build_app`, so there is a single, consistent assembly order - and
neatlogs is initialised here, before any agent object exists, as required."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field, replace
from pathlib import Path

from sololicense.agent.loop import TicketAgent
from sololicense.agent.planner import Planner
from sololicense.connectors import Connectors
from sololicense.agent.worker import RefundWorker
from sololicense.coding.gate import CodingGate
from sololicense.coding.ladder import CodingLadder
from sololicense.config import Config, load_config, with_overrides
from sololicense.db.repositories import settings as settings_repo
from sololicense.db.database import init_db
from sololicense.faults.injector import FaultInjector
from sololicense.observability.neatlogs_client import NeatlogsClient, init_neatlogs
from sololicense.observability.tracer import Tracer
from sololicense.services import economics
from sololicense.services.alerts import AlertNotifier
from sololicense.services.git_ledger import GitLedger
from sololicense.services.license_service import LicenseService
from sololicense.services.policy_service import PolicyService


@dataclass
class AppContext:
    """Fully wired application, ready to serve a UI or a script."""

    config: Config
    conn: sqlite3.Connection
    neatlogs: NeatlogsClient
    worker: RefundWorker
    license_service: LicenseService
    policy_service: PolicyService
    fault_injector: FaultInjector
    alerts: AlertNotifier | None = None
    warnings: list[str] = field(default_factory=list)
    connectors: Connectors | None = None
    agent: TicketAgent | None = None
    coding_gate: CodingGate | None = None


def _local_encryption_key(db_path: Path) -> str:
    """Demo mode only: a per-machine Fernet key next to the database, so a
    stranger can save API keys without generating one first. Production
    deployments must set SOLO_SETTINGS_ENCRYPTION_KEY explicitly."""
    from cryptography.fernet import Fernet

    key_file = db_path.parent / ".settings.key"
    if key_file.exists():
        return key_file.read_text(encoding="ascii").strip()
    key = Fernet.generate_key().decode("ascii")
    key_file.parent.mkdir(parents=True, exist_ok=True)
    key_file.write_text(key, encoding="ascii")
    return key


def build_app(
    config: Config | None = None, *, check_same_thread: bool = True
) -> AppContext:
    config = config or load_config()

    # 1. Persistence first, so operator settings can override the environment.
    conn = init_db(config.db_path, check_same_thread=check_same_thread)
    if not config.settings_encryption_key and config.demo_mode:
        config = replace(
            config, settings_encryption_key=_local_encryption_key(config.db_path)
        )
    warnings: list[str] = []
    stored_settings = settings_repo.get_all(conn)
    try:
        revealed = settings_repo.reveal_secret_values(
            stored_settings, config.settings_encryption_key
        )
    except ValueError as error:
        # A rotated/missing key must not take the whole API down: run without
        # the saved secrets and tell the operator to re-enter them.
        revealed = {
            k: v for k, v in stored_settings.items() if k not in settings_repo.SECRET_KEYS
        }
        warnings.append(f"{error} Re-enter API keys in Settings.")
    config = with_overrides(config, revealed)

    # 2. Observability - instrument before any agent logic.
    neatlogs = init_neatlogs(config)
    tracer = Tracer(neatlogs)

    # 3. Services and the agent.
    alerts = AlertNotifier(
        url=config.alert_webhook_url, business=stored_settings.get("business_name", "")
    )
    license_service = LicenseService(
        conn, GitLedger(repo_root=config.ledger_repo),
        ladder=economics.trust_ladder(revealed, config.trust_confidence),
        on_transition=alerts.notify,
    )
    policy_service = PolicyService(conn, config)
    policy_service.ensure_default_policy()
    fault_injector = FaultInjector(conn)
    planner = Planner(config)
    connectors = Connectors(conn, config)
    worker = RefundWorker(
        conn,
        config,
        tracer=tracer,
        license_service=license_service,
        policy_service=policy_service,
        fault_injector=fault_injector,
        planner=planner,
        connectors=connectors,
    )
    agent = TicketAgent(conn, config, tracer=tracer, worker=worker)
    coding_gate = CodingGate(
        conn, tracer, GitLedger(repo_root=config.ledger_repo),
        ladder=CodingLadder(confidence=config.trust_confidence),
    )

    return AppContext(
        config=config,
        conn=conn,
        neatlogs=neatlogs,
        worker=worker,
        license_service=license_service,
        policy_service=policy_service,
        fault_injector=fault_injector,
        alerts=alerts,
        warnings=warnings,
        connectors=connectors,
        agent=agent,
        coding_gate=coding_gate,
    )
