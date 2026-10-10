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
    llm_provider: str
    anthropic_api_key: str
    anthropic_model: str
    openai_api_key: str
    openai_model: str
    promotion_clean_runs: int
    l2_auto_refund_ceiling: float

    @property
    def llm_enabled(self) -> bool:
        """True when a real model can be called for planning."""
        if self.llm_provider == "anthropic":
            return bool(self.anthropic_api_key)
        if self.llm_provider == "openai":
            return bool(self.openai_api_key)
        return False

    @property
    def neatlogs_enabled(self) -> bool:
        return bool(self.neatlogs_api_key)


def load_config() -> Config:
    """Build a :class:`Config` from the current environment."""
    return Config(
        db_path=Path(_get("SOLO_LICENSE_DB", "data/solo_license.db")),
        neatlogs_api_key=_get("NEATLOGS_API_KEY", ""),
        neatlogs_project=_get("NEATLOGS_PROJECT", "solo-license"),
        llm_provider=_get("LLM_PROVIDER", "deterministic").lower(),
        anthropic_api_key=_get("ANTHROPIC_API_KEY", ""),
        anthropic_model=_get("ANTHROPIC_MODEL", "claude-opus-4-8"),
        openai_api_key=_get("OPENAI_API_KEY", ""),
        openai_model=_get("OPENAI_MODEL", "gpt-4o"),
        promotion_clean_runs=int(_get("PROMOTION_CLEAN_RUNS", "3")),
        l2_auto_refund_ceiling=float(_get("L2_AUTO_REFUND_CEILING", "50")),
    )
