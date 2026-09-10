"""POST /api/auth/disable and /api/auth/enable — turn the operator password
off from the UI, and back on again."""
from __future__ import annotations

import pytest

from backend.auth import service


@pytest.fixture(autouse=True)
def _no_login_delay(monkeypatch):
    import backend.auth.routes as routes
    monkeypatch.setattr(routes, "LOGIN_FAILURE_DELAY_SECONDS", 0)


def _configure(setup_client, password="old-password"):
    """Drive the setup page so the app is file-configured + logged in."""
    assert setup_client.post("/api/auth/setup", json={"password": password}).status_code == 200
    return setup_client


def test_disable_requires_correct_current_password(setup_client):
    c = _configure(setup_client)
    resp = c.post("/api/auth/disable", json={"current": "WRONG-current"})
    assert resp.status_code == 401
    # Still on: the credential survives a rejected attempt.
    assert service.get_password_hash() is not None
    assert not service.password_disabled_in_file()
    assert c.get("/api/auth/status").get_json()["enabled"] is True


def test_disable_success_opens_the_gate(setup_client):
    c = _configure(setup_client)
    resp = c.post("/api/auth/disable", json={"current": "old-password"})
    assert resp.status_code == 200
    assert resp.get_json() == {"disabled": True}

    # The credential is gone, and the opt-out is recorded so a restart does not
    # read "no password" as "run first-boot setup".
    assert service.get_password_hash() is None
    assert service.password_disabled_in_file() is True

    status = c.get("/api/auth/status").get_json()
    assert status["enabled"] is False
    assert status["needs_setup"] is False
    # The session was cleared, yet protected routes are open — that is the
    # point of disabling, and it applies without a restart.
    assert c.get("/api/servers").status_code == 200


def test_disabled_state_survives_a_restart_without_setup_mode(setup_client, setup_app):
    """The flag, not the missing hash, is what a fresh boot must read."""
    c = _configure(setup_client)
    assert c.post("/api/auth/disable", json={"current": "old-password"}).status_code == 200

    # Rebuild the app against the same data dir, as a restart would.
    from backend.auth import init_auth
    import flask
    fresh = flask.Flask(__name__)
    fresh.config["SERVERS_FILE"] = setup_app.config.get("SERVERS_FILE")
    init_auth(fresh)
    assert fresh.config["FABRICATOR_AUTH_ENABLED"] is False
    assert fresh.config["FABRICATOR_NEEDS_SETUP"] is False


def test_disable_requires_json_body(setup_client):
    c = _configure(setup_client)
    resp = c.post(
        "/api/auth/disable",
        data="current=old-password",
        content_type="application/x-www-form-urlencoded",
    )
    assert resp.status_code == 400


def test_disable_requires_session(auth_client):
    # Configured but not logged in -> the gate blocks it before any check.
    assert auth_client.post("/api/auth/disable", json={"current": "x"}).status_code == 401


def test_disable_refused_when_env_managed(authed_client):
    # The env hash wins over the file, so a file flag could not take effect.
    resp = authed_client.post("/api/auth/disable", json={"current": "s3cret-test-pw"})
    assert resp.status_code == 409
    assert service.get_password_hash() is not None


def test_enable_sets_a_password_and_closes_the_gate(setup_client):
    c = _configure(setup_client)
    assert c.post("/api/auth/disable", json={"current": "old-password"}).status_code == 200

    resp = c.post("/api/auth/enable", json={"new": "brand-new-password"})
    assert resp.status_code == 200
    assert resp.get_json() == {"enabled": True}
    # Setting a password clears the opt-out, so the two can never disagree.
    assert service.password_disabled_in_file() is False
    assert service.get_password_hash() is not None

    status = c.get("/api/auth/status").get_json()
    assert status["enabled"] is True
    # enable logs the caller in; the new password is the one that works.
    assert status["authenticated"] is True
    c.post("/api/auth/logout")
    assert c.post("/api/auth/login", json={"password": "old-password"}).status_code == 401
    assert c.post("/api/auth/login", json={"password": "brand-new-password"}).status_code == 200


def test_enable_rejects_a_short_password(setup_client):
    c = _configure(setup_client)
    assert c.post("/api/auth/disable", json={"current": "old-password"}).status_code == 200
    assert c.post("/api/auth/enable", json={"new": "short"}).status_code == 400
    # Still open — a rejected enable must not half-apply.
    assert service.get_password_hash() is None


def test_enable_refused_while_password_is_already_on(setup_client):
    c = _configure(setup_client)
    resp = c.post("/api/auth/enable", json={"new": "brand-new-password"})
    assert resp.status_code == 409
    # The existing credential is untouched.
    c.post("/api/auth/logout")
    assert c.post("/api/auth/login", json={"password": "old-password"}).status_code == 200
