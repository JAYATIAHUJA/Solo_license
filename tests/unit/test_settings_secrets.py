import pytest
from cryptography.fernet import Fernet

from sololicense.db.repositories import settings


def test_secret_settings_are_encrypted_and_round_trip():
    key = Fernet.generate_key().decode("ascii")
    values = {
        "neatlogs_project": "solo-license",
        "neatlogs_api_key": "nlk-live-secret",
    }

    protected = settings.protect_secret_values(values, key)

    assert protected["neatlogs_project"] == "solo-license"
    assert protected["neatlogs_api_key"].startswith("fernet:")
    assert "nlk-live-secret" not in protected["neatlogs_api_key"]
    assert settings.reveal_secret_values(protected, key) == values


def test_secret_settings_require_a_deployment_encryption_key():
    with pytest.raises(ValueError, match="SOLO_SETTINGS_ENCRYPTION_KEY"):
        settings.protect_secret_values({"typesafe_api_key": "ts-secret"}, "")


def test_typesafe_and_neatlogs_keys_are_encrypted_before_storage():
    key = Fernet.generate_key().decode("ascii")
    values = {"typesafe_api_key": "ts-secret", "neatlogs_api_key": "nlk-secret"}

    protected = settings.protect_secret_values(values, key)

    assert all(protected[name].startswith("fernet:") for name in values)
    assert settings.reveal_secret_values(protected, key) == values
