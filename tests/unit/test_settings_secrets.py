import pytest
from cryptography.fernet import Fernet

from sololicense.db.repositories import settings


def test_secret_settings_are_encrypted_and_round_trip():
    key = Fernet.generate_key().decode("ascii")
    values = {
        "llm_provider": "anthropic",
        "anthropic_api_key": "sk-live-secret",
    }

    protected = settings.protect_secret_values(values, key)

    assert protected["llm_provider"] == "anthropic"
    assert protected["anthropic_api_key"].startswith("fernet:")
    assert "sk-live-secret" not in protected["anthropic_api_key"]
    assert settings.reveal_secret_values(protected, key) == values


def test_secret_settings_require_a_deployment_encryption_key():
    with pytest.raises(ValueError, match="SOLO_SETTINGS_ENCRYPTION_KEY"):
        settings.protect_secret_values({"openai_api_key": "sk-secret"}, "")


def test_groq_and_zcode_keys_are_encrypted_before_storage():
    key = Fernet.generate_key().decode("ascii")
    values = {"groq_api_key": "gsk-secret", "zcode_api_key": "zcode-secret"}

    protected = settings.protect_secret_values(values, key)

    assert all(protected[name].startswith("fernet:") for name in values)
    assert settings.reveal_secret_values(protected, key) == values
