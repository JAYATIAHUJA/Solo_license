"""Composition root.

The one place where concrete dependencies are constructed and wired. The API,
the CLI and the scripts build their world through :func:`build_app`, so there
is a single, consistent assembly order - and neatlogs is initialised here,
before the coding gate exists, as required."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field, replace
from pathlib import Path

from sololicense.coding.gate import CodingGate
from sololicense.coding.jev import JevClient
from sololicense.coding.ladder import CodingLadder
from sololicense.coding.verify import check_turn
from sololicense.config import Config, load_config, with_overrides
from sololicense.db.repositories import settings as settings_repo
from sololicense.db.database import init_db
from sololicense.observability.neatlogs_client import NeatlogsClient, init_neatlogs
from sololicense.observability.tracer import Tracer
from sololicense.services.git_ledger import GitLedger


@dataclass
class AppContext:
    """Fully wired application, ready to serve the API or a script."""

    config: Config
    conn: sqlite3.Connection
    neatlogs: NeatlogsClient
    coding_gate: CodingGate | None = None
    warnings: list[str] = field(default_factory=list)


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

    # 2. Observability - instrument before any gate logic.
    neatlogs = init_neatlogs(config)
    tracer = Tracer(neatlogs)

    # 3. The coding gate.
    coding_gate = CodingGate(
        conn, tracer, GitLedger(repo_root=config.ledger_repo),
        ladder=CodingLadder(confidence=config.trust_confidence),
        verifier=check_turn,
        jev_client=JevClient(api_key=config.typesafe_api_key, endpoint=config.jev_endpoint),
    )

    return AppContext(
        config=config,
        conn=conn,
        neatlogs=neatlogs,
        coding_gate=coding_gate,
        warnings=warnings,
    )
