"""Session cookie flags — a security toggle with no test silently no-ops."""
from __future__ import annotations


def test_cookie_flags_default(auth_client):
    resp = auth_client.post("/api/auth/login", json={"password": "s3cret-test-pw"})
    assert resp.status_code == 200
    cookie = resp.headers.get("Set-Cookie", "")
    assert "HttpOnly" in cookie
    assert "SameSite=Lax" in cookie
    assert "Secure" not in cookie  # default off — panel serves HTTP


def test_cookie_secure_when_enabled(tmp_servers_root, monkeypatch):
    from backend.auth import service

    monkeypatch.delenv("FABRICATOR_DISABLE_AUTH", raising=False)
    monkeypatch.setenv("SECRET_KEY", "test-secret-key")
    monkeypatch.setenv("FABRICATOR_AUTH_PASSWORD_HASH", service.hash_password("pw"))
    monkeypatch.setenv("FABRICATOR_SESSION_COOKIE_SECURE", "1")

    import backend.server.registry as registry_mod
    registry_mod.reset_for_tests()
    from backend.core.app import create_app

    app = create_app()
    app.config["TESTING"] = True
    resp = app.test_client().post("/api/auth/login", json={"password": "pw"})
    cookie = resp.headers.get("Set-Cookie", "")
    assert "Secure" in cookie
    assert "HttpOnly" in cookie
