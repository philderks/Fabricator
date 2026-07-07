"""Setup mode: an unconfigured app boots LOCKED (no longer raises), and the
gate hard-locks everything except the setup allowlist. The only hard-fail left
is an un-writable data dir.
"""
from __future__ import annotations

import pytest


def _build():
    import backend.server.registry as registry_mod
    registry_mod.reset_for_tests()
    from backend.core.app import create_app
    return create_app()


def test_unconfigured_boots_into_setup_mode(setup_app):
    # No RuntimeError anymore — enabled-but-unconfigured boots locked.
    assert setup_app.config["FABRICATOR_AUTH_ENABLED"] is True
    assert setup_app.config["FABRICATOR_NEEDS_SETUP"] is True


def test_setup_mode_gate_locks_everything_except_allowlist(setup_client):
    # Hard lockdown: status + health reachable; everything else 401.
    assert setup_client.get("/api/auth/status").status_code == 200
    assert setup_client.get("/api/health").status_code == 200
    assert setup_client.get("/api/servers").status_code == 401
    # Even a normal login is not available before a credential exists.
    assert setup_client.post("/api/auth/login", json={"password": "x"}).status_code == 401


def test_configured_via_env_is_not_setup_mode(tmp_servers_root, monkeypatch):
    from backend.auth import service
    monkeypatch.delenv("FABRICATOR_DISABLE_AUTH", raising=False)
    monkeypatch.setenv("SECRET_KEY", "k")
    monkeypatch.setenv("FABRICATOR_AUTH_PASSWORD_HASH", service.hash_password("x"))
    app = _build()
    assert app.config["FABRICATOR_AUTH_ENABLED"] is True
    assert app.config["FABRICATOR_NEEDS_SETUP"] is False


def test_unwritable_data_dir_raises(tmp_servers_root, monkeypatch):
    # The one remaining hard-fail: the key/credential cannot be persisted.
    from backend.auth import service
    monkeypatch.delenv("FABRICATOR_DISABLE_AUTH", raising=False)
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.delenv("FABRICATOR_AUTH_PASSWORD_HASH", raising=False)
    monkeypatch.setattr(service, "data_dir_writable", lambda: False)
    with pytest.raises(RuntimeError) as exc:
        _build()
    assert "not writable" in str(exc.value).lower()
