"""The MCP block in auth.json: the on/off switch and its fail-safe defaults."""
from __future__ import annotations

import json

from backend.auth import service


def test_mcp_state_defaults_off_with_no_tokens(tmp_servers_root):
    # No auth.json at all -> the switch reads OFF and the token map is empty.
    state = service.mcp_state()
    assert state == {"enabled": False, "tokens": {}}


def test_set_mcp_enabled_persists(tmp_servers_root):
    service.set_mcp_enabled(True)
    assert service.mcp_state()["enabled"] is True
    service.set_mcp_enabled(False)
    assert service.mcp_state()["enabled"] is False


def test_set_mcp_enabled_preserves_credential_and_key(tmp_servers_root, monkeypatch):
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.delenv("FABRICATOR_AUTH_PASSWORD_HASH", raising=False)
    key = service.load_or_create_secret_key()
    service.set_password("pw")
    service.set_mcp_enabled(True)  # must not clobber secret_key / password_hash
    data = json.loads((tmp_servers_root / "auth.json").read_text(encoding="utf-8"))
    assert data["secret_key"] == key
    assert "password_hash" in data
    assert data["mcp"]["enabled"] is True
    assert data["mcp"]["tokens"] == {}
    assert service.verify_password("pw") is True


def test_mcp_block_malformed_is_failsafe_off(tmp_servers_root):
    # SECURITY: a non-dict or otherwise malformed mcp block must never enable
    # token auth — it reads as OFF with no tokens.
    service._write_auth_file({"mcp": "garbage", "tokens": 5})
    assert service.mcp_state() == {"enabled": False, "tokens": {}}
    service._write_auth_file({"mcp": {"enabled": True, "tokens": "not-a-dict"}})
    assert service.mcp_state() == {"enabled": True, "tokens": {}}
