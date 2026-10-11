"""Runtime configuration, loaded once from the environment (and ``.env``).

Every setting has a default that makes the demo runnable with an empty
environment. Secrets stay in the environment and are never logged."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:  # dotenv is a convenience; the app still runs without it.
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover - optional dependency
    pass


def _get(name: str, default: str) -> str:
    value = os.environ.get(name, "").strip()
    return value or default


@dataclass(frozen=True)
class Config:
    """Immutable snapshot of configuration for one process."""

    db_path: Path
    neatlogs_api_key: str
    neatlogs_project: str
    ledger_repo: Path
    settings_encryption_key: str
    demo_mode: bool = False
    neatlogs_endpoint: str = "https://ingest.neatlogs.com"
    neatlogs_app_url: str = "https://app.neatlogs.com"
    # How sure the evidence must be before an action class climbs a rung.
    trust_confidence: float = 0.9
    # Jev (TypeSafe AI) for calibrated gate decisions; optional.
    typesafe_api_key: str = ""
    jev_endpoint: str = "https://api.typesafe.ai/v1/systemone"

    @property
    def neatlogs_enabled(self) -> bool:
        return bool(self.neatlogs_api_key)


def _truthy(value: str) -> bool:
    return value.strip().lower() in ("1", "true", "yes", "on")


def load_config() -> Config:
    """Build a :class:`Config` from the current environment."""
    return Config(
        db_path=Path(_get("SOLO_LICENSE_DB", "data/solo_license.db")),
        neatlogs_api_key=_get("NEATLOGS_API_KEY", ""),
        neatlogs_project=_get("NEATLOGS_PROJECT", "solo-license"),
        ledger_repo=Path(_get("SOLO_LEDGER_REPO", "data/ledger-repo")),
        settings_encryption_key=_get("SOLO_SETTINGS_ENCRYPTION_KEY", ""),
        demo_mode=_truthy(_get("SOLO_DEMO_MODE", "0")),
        neatlogs_endpoint=_get("NEATLOGS_ENDPOINT", "https://ingest.neatlogs.com"),
        neatlogs_app_url=_get("NEATLOGS_APP_URL", "https://app.neatlogs.com"),
        trust_confidence=_clamp(float(_get("TRUST_CONFIDENCE", "0.9")), 0.5, 0.999),
        typesafe_api_key=_get("TYPESAFE_API_KEY", _get("JEV_API_KEY", "")),
        jev_endpoint=_get("JEV_ENDPOINT", "https://api.typesafe.ai/v1/systemone"),
    )


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


_STR_KEYS = ("neatlogs_api_key", "neatlogs_project", "typesafe_api_key", "jev_endpoint")


def with_overrides(config: Config, stored: dict[str, str]) -> Config:
    """Overlay operator settings (from the settings table) on env defaults."""
    from dataclasses import replace

    changes: dict[str, object] = {}
    for key in _STR_KEYS:
        if stored.get(key, "").strip():
            changes[key] = stored[key].strip()
    if stored.get("trust_confidence", "").strip():
        changes["trust_confidence"] = _clamp(float(stored["trust_confidence"]), 0.5, 0.999)
    return replace(config, **changes)
