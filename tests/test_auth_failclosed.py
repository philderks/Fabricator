"""Fail-closed: enabled-but-unconfigured refuses to start (every env)."""
from __future__ import annotations

import pytest


def _build():
    import backend.server.registry as registry_mod
    registry_mod.reset_for_tests()
    from backend.core.app import create_app
    return create_app()


def test_failclosed_missing_secret(tmp_servers_root, monkeypatch):
    from backend.auth import service
    monkeypatch.delenv("FABRICATOR_DISABLE_AUTH", raising=False)
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.setenv("FABRICATOR_AUTH_PASSWORD_HASH", service.hash_password("x"))
    with pytest.raises(RuntimeError) as exc:
        _build()
    assert "SECRET_KEY" in str(exc.value)


def test_failclosed_missing_hash(tmp_servers_root, monkeypatch):
    monkeypatch.delenv("FABRICATOR_DISABLE_AUTH", raising=False)
    monkeypatch.setenv("SECRET_KEY", "k")
    monkeypatch.delenv("FABRICATOR_AUTH_PASSWORD_HASH", raising=False)
    with pytest.raises(RuntimeError) as exc:
        _build()
    assert "FABRICATOR_AUTH_PASSWORD_HASH" in str(exc.value)


def test_failclosed_message_names_both_commands(tmp_servers_root, monkeypatch):
    monkeypatch.delenv("FABRICATOR_DISABLE_AUTH", raising=False)
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.delenv("FABRICATOR_AUTH_PASSWORD_HASH", raising=False)
    with pytest.raises(RuntimeError) as exc:
        _build()
    msg = str(exc.value)
    assert "fabricator hash-password" in msg
    assert "python -m backend.auth hash" in msg


def test_configured_boots(tmp_servers_root, monkeypatch):
    from backend.auth import service
    monkeypatch.delenv("FABRICATOR_DISABLE_AUTH", raising=False)
    monkeypatch.setenv("SECRET_KEY", "k")
    monkeypatch.setenv("FABRICATOR_AUTH_PASSWORD_HASH", service.hash_password("x"))
    app = _build()  # must NOT raise
    assert app.config["FABRICATOR_AUTH_ENABLED"] is True
