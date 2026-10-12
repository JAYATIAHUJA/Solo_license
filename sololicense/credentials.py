"""This machine's own credentials: the settings encryption key and the first
admin token, made once by ``solo-license onboard`` so nobody writes
``SOLO_API_TOKENS`` or ``SOLO_SETTINGS_ENCRYPTION_KEY`` by hand.

Stored in the macOS Keychain when it is available, otherwise in
``~/.solo-license/credentials.json`` readable only by this user (0600).
``solo-license serve`` loads them into its environment; values already set in
the environment always win.
"""

from __future__ import annotations

import getpass
import json
import os
import secrets
import shutil
import subprocess
import sys
from pathlib import Path

KEYCHAIN_SERVICE = "solo-license"
KEYCHAIN_ACCOUNT = "local-admin"


def home() -> Path:
    return Path(os.environ.get("SOLO_LICENSE_HOME", Path.home() / ".solo-license"))


def path() -> Path:
    return home() / "credentials.json"


def _keychain_available() -> bool:
    return sys.platform == "darwin" and shutil.which("security") is not None


def _keychain_read() -> dict | None:
    try:
        out = subprocess.run(["security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-a", KEYCHAIN_ACCOUNT,
                              "-w"], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    try:
        return json.loads(out.stdout.strip())
    except json.JSONDecodeError:
        return None


def _keychain_write(creds: dict) -> bool:
    try:
        out = subprocess.run(["security", "add-generic-password", "-U", "-s", KEYCHAIN_SERVICE, "-a",
                              KEYCHAIN_ACCOUNT, "-w", json.dumps(creds)], capture_output=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return False
    return out.returncode == 0


def _write_private(target: Path, data: dict) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    try:
        os.chmod(target, 0o600)  # also when the file already existed
    except OSError:
        pass


def load() -> dict | None:
    """The stored credentials, or None if onboarding has not made them yet."""
    try:
        marker = json.loads(path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if marker.get("store") == "keychain":
        return _keychain_read()
    if not marker.get("admin_token"):
        return None
    return {k: v for k, v in marker.items() if k != "store"}


def ensure() -> tuple[dict, str]:
    """Load the credentials, or make them. Returns (credentials, where they are kept)."""
    from cryptography.fernet import Fernet

    existing = load()
    if existing:
        return existing, describe()
    creds = {
        "admin_id": f"local:{getpass.getuser() or 'admin'}",
        "admin_token": secrets.token_urlsafe(32),
        "settings_encryption_key": Fernet.generate_key().decode("ascii"),
    }
    if _keychain_available() and _keychain_write(creds):
        _write_private(path(), {"store": "keychain", "service": KEYCHAIN_SERVICE, "account": KEYCHAIN_ACCOUNT})
    else:
        _write_private(path(), {"store": "file", **creds})
    return creds, describe()


def describe() -> str:
    try:
        marker = json.loads(path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "not created yet"
    if marker.get("store") == "keychain":
        return f"macOS Keychain (service '{KEYCHAIN_SERVICE}')"
    return f"{path()} (readable only by you)"


def apply_env(creds: dict | None = None) -> bool:
    """Put the stored credentials into this process's environment for the gate."""
    creds = creds or load()
    if not creds:
        return False
    os.environ.setdefault("SOLO_SETTINGS_ENCRYPTION_KEY", creds["settings_encryption_key"])
    if not os.environ.get("SOLO_API_TOKENS", "").strip():
        os.environ["SOLO_API_TOKENS"] = json.dumps(
            {creds["admin_token"]: {"id": creds["admin_id"], "role": "admin"}})
    return True
