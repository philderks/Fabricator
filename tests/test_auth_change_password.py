"""POST /api/auth/change-password — rotate the operator password (file mode)."""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _no_login_delay(monkeypatch):
    import backend.auth.routes as routes
    monkeypatch.setattr(routes, "LOGIN_FAILURE_DELAY_SECONDS", 0)


def _configure(setup_client, password="old-password"):
    """Drive the setup page so the app is file-configured + logged in."""
    assert setup_client.post("/api/auth/setup", json={"password": password}).status_code == 200
    return setup_client


def test_change_password_success(setup_client):
    c = _configure(setup_client)
    resp = c.post(
        "/api/auth/change-password",
        json={"current": "old-password", "new": "new-password-x"},
    )
    assert resp.status_code == 200
    assert resp.get_json() == {"changed": True}
    # New password works, old does not.
    c.post("/api/auth/logout")
    assert c.post("/api/auth/login", json={"password": "old-password"}).status_code == 401
    assert c.post("/api/auth/login", json={"password": "new-password-x"}).status_code == 200


def test_change_password_wrong_current_unchanged(setup_client):
    c = _configure(setup_client)
    resp = c.post(
        "/api/auth/change-password",
        json={"current": "WRONG-current", "new": "new-password-x"},
    )
    assert resp.status_code == 401
    # Unchanged: the old password still works.
    c.post("/api/auth/logout")
    assert c.post("/api/auth/login", json={"password": "old-password"}).status_code == 200


def test_change_password_short_new(setup_client):
    c = _configure(setup_client)
    assert c.post(
        "/api/auth/change-password", json={"current": "old-password", "new": "short"}
    ).status_code == 400


def test_change_password_requires_json(setup_client):
    c = _configure(setup_client)
    resp = c.post(
        "/api/auth/change-password",
        data="current=old-password&new=new-password-x",
        content_type="application/x-www-form-urlencoded",
    )
    assert resp.status_code == 400


def test_change_password_requires_session(auth_client):
    # Configured (env hash) but NOT logged in -> the gate blocks it.
    assert auth_client.post(
        "/api/auth/change-password", json={"current": "x", "new": "yyyyyyyy"}
    ).status_code == 401


def test_change_password_refused_when_env_managed(authed_client):
    # authed_client uses the ENV hash (declarative). A UI change can't apply, so
    # the endpoint refuses with 409 even though the session is valid.
    resp = authed_client.post(
        "/api/auth/change-password",
        json={"current": "s3cret-test-pw", "new": "new-password-x"},
    )
    assert resp.status_code == 409
