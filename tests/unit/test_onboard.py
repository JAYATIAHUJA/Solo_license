import json
import os
import stat

from fastapi.testclient import TestClient

from sololicense import credentials, onboard


def test_credentials_are_made_once_privately_and_reach_the_gate(tmp_path, monkeypatch):
    monkeypatch.setenv("SOLO_LICENSE_HOME", str(tmp_path))
    monkeypatch.setattr(credentials, "_keychain_available", lambda: False)
    monkeypatch.delenv("SOLO_API_TOKENS", raising=False)
    monkeypatch.delenv("SOLO_SETTINGS_ENCRYPTION_KEY", raising=False)

    creds, where = credentials.ensure()
    assert str(tmp_path) in where and creds["admin_token"] and creds["settings_encryption_key"]
    if os.name != "nt":
        assert stat.S_IMODE(os.stat(credentials.path()).st_mode) == 0o600
    assert credentials.ensure()[0] == creds  # made once

    assert credentials.apply_env()
    tokens = json.loads(os.environ["SOLO_API_TOKENS"])
    assert tokens[creds["admin_token"]] == {"id": creds["admin_id"], "role": "admin"}
    assert os.environ["SOLO_SETTINGS_ENCRYPTION_KEY"] == creds["settings_encryption_key"]


def test_tokens_already_in_the_environment_win(tmp_path, monkeypatch):
    monkeypatch.setenv("SOLO_LICENSE_HOME", str(tmp_path))
    monkeypatch.setattr(credentials, "_keychain_available", lambda: False)
    monkeypatch.setenv("SOLO_API_TOKENS", '{"t":{"id":"ops","role":"admin"}}')
    credentials.ensure()
    credentials.apply_env()
    assert json.loads(os.environ["SOLO_API_TOKENS"]) == {"t": {"id": "ops", "role": "admin"}}


def test_no_credentials_means_nothing_applied(tmp_path, monkeypatch):
    monkeypatch.setenv("SOLO_LICENSE_HOME", str(tmp_path))
    assert credentials.load() is None and not credentials.apply_env()


def test_verify_gate_sends_a_harmless_read(tmp_path):
    sent = {}

    def post(url, body):
        sent.update(url=url, body=body)
        return {"hookSpecificOutput": {"permissionDecision": "allow"}}

    ok, how = onboard.verify_gate("http://127.0.0.1:8000", tmp_path, post)
    assert ok and "allow" in how
    assert sent["url"].endswith("/api/hooks/pre-tool") and sent["body"]["tool_name"] == "Read"
    assert onboard.verify_gate("http://x", tmp_path, lambda u, b: None)[0] is False


def test_integrations_are_optional_steps(monkeypatch):
    monkeypatch.setattr(onboard.shutil, "which", lambda name: None)
    lines = onboard.integrations({"neatlogs_enabled": True})
    assert lines[0].endswith("connected") and "optional" in lines[1] and "optional" in lines[2]


def test_the_gate_serves_the_built_dashboard(tmp_path, monkeypatch):
    from sololicense.api import app as app_module

    (tmp_path / "index.html").write_text('<div id="root"></div>', encoding="utf-8")
    (tmp_path / "app.js").write_text("console.log(1)", encoding="utf-8")
    monkeypatch.setenv("SOLO_DASHBOARD_DIR", str(tmp_path))
    client = TestClient(app_module.app)
    assert 'id="root"' in client.get("/onboarding").text
    assert client.get("/app.js").text == "console.log(1)"
    assert client.get("/api/no-such-route").status_code == 404
    assert 'id="root"' in client.get("/../../etc/passwd").text  # never leaves the dashboard folder
