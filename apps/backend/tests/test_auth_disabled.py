"""Explicit opt-out + the fail-safe FABRICATOR_DISABLE_AUTH=0 invariant."""
from __future__ import annotations


def _build():
    import backend.server.registry as registry_mod
    registry_mod.reset_for_tests()
    from backend.core.app import create_app
    return create_app()


def test_disabled_boots_without_credential(tmp_servers_root, monkeypatch):
    # tmp_servers_root already sets FABRICATOR_DISABLE_AUTH=1.
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.delenv("FABRICATOR_AUTH_PASSWORD_HASH", raising=False)
    app = _build()  # must NOT raise
    client = app.test_client()
    assert client.get("/api/servers").status_code == 200  # reachable, no login


def test_disable_auth_zero_still_enforces(tmp_servers_root, monkeypatch):
    """SECURITY: FABRICATOR_DISABLE_AUTH=0 must NOT disable auth."""
    from backend.auth import service
    monkeypatch.setenv("FABRICATOR_DISABLE_AUTH", "0")
    monkeypatch.setenv("SECRET_KEY", "k")
    monkeypatch.setenv("FABRICATOR_AUTH_PASSWORD_HASH", service.hash_password("x"))
    app = _build()
    assert app.config["FABRICATOR_AUTH_ENABLED"] is True
    assert app.test_client().get("/api/servers").status_code == 401  # enforced!
