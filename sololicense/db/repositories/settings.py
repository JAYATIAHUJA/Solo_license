"""Settings repository - operator-editable key/value configuration."""

from __future__ import annotations

import sqlite3

from cryptography.fernet import Fernet, InvalidToken


SECRET_KEYS = frozenset({
    "anthropic_api_key", "openai_api_key", "gemini_api_key", "groq_api_key",
    "zcode_api_key", "compat_api_key",
    "neatlogs_api_key", "alert_webhook_url", "stripe_secret_key", "inbox_secret",
    "typesafe_api_key",
})
_PREFIX = "fernet:"


def get_all(conn: sqlite3.Connection) -> dict[str, str]:
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    return {row["key"]: row["value"] for row in rows}


def set_many(conn: sqlite3.Connection, values: dict[str, str]) -> None:
    """Upsert several settings. The caller commits."""
    conn.executemany(
        """
        INSERT INTO settings (key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value,
                                       updated_at = datetime('now')
        """,
        list(values.items()),
    )


def protect_secret_values(values: dict[str, str], encryption_key: str) -> dict[str, str]:
    """Encrypt secret settings before they are persisted in SQLite."""
    secret_values = SECRET_KEYS.intersection(values)
    if secret_values and not encryption_key:
        raise ValueError("SOLO_SETTINGS_ENCRYPTION_KEY is required to save secrets.")
    if not secret_values:
        return dict(values)
    try:
        fernet = Fernet(encryption_key.encode("ascii"))
    except (ValueError, UnicodeEncodeError) as error:
        raise ValueError("SOLO_SETTINGS_ENCRYPTION_KEY is not a valid Fernet key.") from error

    protected = dict(values)
    for key in secret_values:
        protected[key] = _PREFIX + fernet.encrypt(values[key].encode("utf-8")).decode("ascii")
    return protected


def reveal_secret_values(values: dict[str, str], encryption_key: str) -> dict[str, str]:
    """Decrypt encrypted settings for process-local configuration only.

    Legacy plaintext values are returned unchanged so a later save can migrate
    them. New writes always use :func:`protect_secret_values`.
    """
    encrypted_keys = [
        key for key in SECRET_KEYS if values.get(key, "").startswith(_PREFIX)
    ]
    if not encrypted_keys:
        return dict(values)
    if not encryption_key:
        raise ValueError("SOLO_SETTINGS_ENCRYPTION_KEY is required to read saved secrets.")
    try:
        fernet = Fernet(encryption_key.encode("ascii"))
        revealed = dict(values)
        for key in encrypted_keys:
            revealed[key] = fernet.decrypt(values[key][len(_PREFIX):].encode("ascii")).decode("utf-8")
        return revealed
    except (InvalidToken, UnicodeDecodeError, ValueError) as error:
        raise ValueError("Saved settings secrets cannot be decrypted.") from error
