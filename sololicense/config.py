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
    gemini_api_key: str
    gemini_model: str
    groq_api_key: str
    groq_model: str
    zcode_api_key: str
    zcode_model: str
    compat_api_key: str
    compat_model: str
    compat_base_url: str
    l2_auto_refund_ceiling: float
    ledger_repo: Path
    settings_encryption_key: str
    llm_timeout_seconds: float
    llm_max_retries: int
    l2_auto_credit_ceiling: float = 75.0
    alert_webhook_url: str = ""
    demo_mode: bool = False
    neatlogs_endpoint: str = "https://ingest.neatlogs.com"
    neatlogs_app_url: str = "https://app.neatlogs.com"
    neatlogs_trace_url: str = "{app}/traces/{trace_id}"
    # How sure the evidence must be before a job type climbs a rung.
    trust_confidence: float = 0.9
    # Refund policy the agent checks before acting.
    refund_window_days: int = 30
    # Connectors.
    stripe_secret_key: str = ""
    stripe_api_base: str = "https://api.stripe.com"
    inbox_secret: str = ""

    @property
    def llm_api_key(self) -> str:
        spec = PROVIDERS.get(self.llm_provider)
        return getattr(self, spec.key_field) if spec and spec.key_field else ""

    @property
    def llm_model(self) -> str:
        spec = PROVIDERS.get(self.llm_provider)
        return getattr(self, spec.model_field) if spec and spec.model_field else "deterministic"

    @property
    def llm_base_url(self) -> str | None:
        """Endpoint for OpenAI-compatible providers, if one is required."""
        spec = PROVIDERS.get(self.llm_provider)
        if spec is None:
            return None
        if spec.base_url:
            return spec.base_url
        return self.compat_base_url if spec.needs_base_url else None

    @property
    def llm_enabled(self) -> bool:
        """True when a real model can be called for planning."""
        spec = PROVIDERS.get(self.llm_provider)
        if spec is None or spec.key_field is None:
            return False
        if spec.needs_base_url and not self.compat_base_url:
            return False
        return bool(self.llm_api_key)

    def ceiling_for(self, task_class: str) -> float:
        """L2 auto-execute ceiling for a task class (one setting per class)."""
        if task_class == "store_credit":
            return self.l2_auto_credit_ceiling
        return self.l2_auto_refund_ceiling

    @property
    def neatlogs_enabled(self) -> bool:
        return bool(self.neatlogs_api_key)


@dataclass(frozen=True)
class ProviderSpec:
    """One LLM provider: which config fields hold its key and model."""

    label: str
    key_field: str | None
    model_field: str | None
    default_model: str = ""
    base_url: str | None = None
    needs_base_url: bool = False


# The single registry of model providers. The API serves it to the UI so the
# onboarding form never hard-codes a provider list of its own.
PROVIDERS: dict[str, ProviderSpec] = {
    "deterministic": ProviderSpec("Built-in rules (no key)", None, None),
    "gemini": ProviderSpec("Google Gemini", "gemini_api_key", "gemini_model", "gemini-2.5-flash"),
    "anthropic": ProviderSpec("Anthropic Claude", "anthropic_api_key", "anthropic_model", "claude-sonnet-5-5"),
    "openai": ProviderSpec("OpenAI", "openai_api_key", "openai_model", "gpt-4o"),
    "groq": ProviderSpec(
        "Groq", "groq_api_key", "groq_model", "llama-3.3-70b-versatile",
        base_url="https://api.groq.com/openai/v1",
    ),
    "zcode_glm": ProviderSpec(
        "ZCode GLM", "zcode_api_key", "zcode_model", "glm-5.3",
        base_url="https://api.z.ai/api/coding/paas/v4",
    ),
    "openai_compatible": ProviderSpec(
        "Other OpenAI-compatible provider", "compat_api_key", "compat_model", "",
        needs_base_url=True,
    ),
}


def _truthy(value: str) -> bool:
    return value.strip().lower() in ("1", "true", "yes", "on")


def load_config() -> Config:
    """Build a :class:`Config` from the current environment."""
    return Config(
        db_path=Path(_get("SOLO_LICENSE_DB", "data/solo_license.db")),
        neatlogs_api_key=_get("NEATLOGS_API_KEY", ""),
        neatlogs_project=_get("NEATLOGS_PROJECT", "solo-license"),
        llm_provider=_get("LLM_PROVIDER", "deterministic").lower(),
        anthropic_api_key=_get("ANTHROPIC_API_KEY", ""),
        anthropic_model=_get("ANTHROPIC_MODEL", PROVIDERS["anthropic"].default_model),
        openai_api_key=_get("OPENAI_API_KEY", ""),
        openai_model=_get("OPENAI_MODEL", PROVIDERS["openai"].default_model),
        gemini_api_key=_get("GEMINI_API_KEY", _get("GOOGLE_API_KEY", "")),
        gemini_model=_get("GEMINI_MODEL", PROVIDERS["gemini"].default_model),
        groq_api_key=_get("GROQ_API_KEY", ""),
        groq_model=_get("GROQ_MODEL", PROVIDERS["groq"].default_model),
        zcode_api_key=_get("ZCODE_API_KEY", ""),
        zcode_model=_get("ZCODE_MODEL", PROVIDERS["zcode_glm"].default_model),
        compat_api_key=_get("OPENAI_COMPATIBLE_API_KEY", ""),
        compat_model=_get("OPENAI_COMPATIBLE_MODEL", ""),
        compat_base_url=_get("OPENAI_COMPATIBLE_BASE_URL", ""),
        l2_auto_refund_ceiling=float(_get("L2_AUTO_REFUND_CEILING", "50")),
        ledger_repo=Path(_get("SOLO_LEDGER_REPO", "data/ledger-repo")),
        settings_encryption_key=_get("SOLO_SETTINGS_ENCRYPTION_KEY", ""),
        llm_timeout_seconds=max(1.0, float(_get("LLM_TIMEOUT_SECONDS", "15"))),
        llm_max_retries=max(0, int(_get("LLM_MAX_RETRIES", "2"))),
        l2_auto_credit_ceiling=float(_get("L2_AUTO_CREDIT_CEILING", "75")),
        alert_webhook_url=_get("SOLO_ALERT_WEBHOOK_URL", ""),
        demo_mode=_truthy(_get("SOLO_DEMO_MODE", "0")),
        neatlogs_endpoint=_get("NEATLOGS_ENDPOINT", "https://ingest.neatlogs.com"),
        neatlogs_app_url=_get("NEATLOGS_APP_URL", "https://app.neatlogs.com"),
        neatlogs_trace_url=_get("NEATLOGS_TRACE_URL", "{app}/traces/{trace_id}"),
        trust_confidence=_clamp(float(_get("TRUST_CONFIDENCE", "0.9")), 0.5, 0.999),
        refund_window_days=max(0, int(_get("REFUND_WINDOW_DAYS", "30"))),
        stripe_secret_key=_get("STRIPE_SECRET_KEY", ""),
        stripe_api_base=_get("STRIPE_API_BASE", "https://api.stripe.com"),
        inbox_secret=_get("SOLO_INBOX_SECRET", ""),
    )


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


_STR_KEYS = (
    "llm_provider", "anthropic_api_key", "anthropic_model",
    "openai_api_key", "openai_model", "gemini_api_key", "gemini_model",
    "groq_api_key", "groq_model", "zcode_api_key", "zcode_model",
    "compat_api_key", "compat_model", "compat_base_url",
    "neatlogs_api_key", "neatlogs_project", "alert_webhook_url",
    "stripe_secret_key", "inbox_secret",
)


def with_overrides(config: Config, stored: dict[str, str]) -> Config:
    """Overlay operator settings (from the settings table) on env defaults."""
    from dataclasses import replace

    changes: dict[str, object] = {}
    for key in _STR_KEYS:
        if stored.get(key, "").strip():
            changes[key] = stored[key].strip()
    if stored.get("trust_confidence", "").strip():
        changes["trust_confidence"] = _clamp(float(stored["trust_confidence"]), 0.5, 0.999)
    if stored.get("refund_window_days", "").strip():
        changes["refund_window_days"] = max(0, int(float(stored["refund_window_days"])))
    if stored.get("l2_auto_refund_ceiling", "").strip():
        changes["l2_auto_refund_ceiling"] = max(0.0, float(stored["l2_auto_refund_ceiling"]))
    if stored.get("l2_auto_credit_ceiling", "").strip():
        changes["l2_auto_credit_ceiling"] = max(0.0, float(stored["l2_auto_credit_ceiling"]))
    return replace(config, **changes)
