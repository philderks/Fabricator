"""POST /api/auth/setup — first-boot credential: one-time + JSON-only (CSRF)."""
from __future__ import annotations

import json


def _build():
    import backend.server.registry as registry_mod
    registry_mod.reset_for_tests()
    from backend.core.app import create_app
    return create_app()


def test_setup_success_writes_hash_and_logs_in(setup_app, setup_client):
    resp = setup_client.post("/api/auth/setup", json={"password": "operator-pw"})
    assert resp.status_code == 200
    assert resp.get_json() == {"authenticated": True}
    # needs_setup flipped off in-memory, and we're logged in (no re-login).
    assert setup_app.config["FABRICATOR_NEEDS_SETUP"] is False
    assert setup_client.get("/api/servers").status_code == 200
    assert setup_client.get("/api/auth/status").get_json() == {
        "enabled": True,
        "authenticated": True,
        "needs_setup": False,
        "managed": False,
    }


def test_setup_one_time_flag_and_exists_guard(setup_app, setup_client, monkeypatch):
    import backend.auth.routes as routes
    monkeypatch.setattr(routes, "LOGIN_FAILURE_DELAY_SECONDS", 0)

    assert setup_client.post(
        "/api/auth/setup", json={"password": "first-pw-xx"}
    ).status_code == 200
    # (a) the in-memory flag flipped -> a second setup is refused.
    assert setup_client.post(
        "/api/auth/setup", json={"password": "second-pwx"}
    ).status_code == 409
    # (b) exists-guard: even with a STALE needs_setup flag (simulated race /
    #     restart), complete_setup refuses because a credential already exists.
    setup_app.config["FABRICATOR_NEEDS_SETUP"] = True
    assert setup_client.post(
        "/api/auth/setup", json={"password": "third-pwxx"}
    ).status_code == 409
    # The credential is still the FIRST password — never overwritten.
    setup_app.config["FABRICATOR_NEEDS_SETUP"] = False  # back to configured
    assert setup_client.post(
        "/api/auth/login", json={"password": "second-pwx"}
    ).status_code == 401
    assert setup_client.post(
        "/api/auth/login", json={"password": "first-pw-xx"}
    ).status_code == 200


def test_setup_requires_json_not_form(setup_client):
    # A form-encoded body -> 400 (closes pre-auth CSRF on this state-changer).
    resp = setup_client.post(
        "/api/auth/setup",
        data="password=operator-pw",
        content_type="application/x-www-form-urlencoded",
    )
    assert resp.status_code == 400


def test_setup_rejects_short_or_missing_password(setup_client):
    assert setup_client.post(
        "/api/auth/setup", json={"password": "short"}
    ).status_code == 400
    assert setup_client.post("/api/auth/setup", json={}).status_code == 400


def test_setup_409_when_already_configured(authed_client):
    # Configured + authenticated: the gate allows the request through; the
    # handler refuses because setup is over.
    assert authed_client.post(
        "/api/auth/setup", json={"password": "whatever-x"}
    ).status_code == 409


def test_setup_preserves_secret_key_across_restart(tmp_servers_root, monkeypatch):
    monkeypatch.delenv("FABRICATOR_DISABLE_AUTH", raising=False)
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.delenv("FABRICATOR_AUTH_PASSWORD_HASH", raising=False)

    # First boot: setup mode; key generated + persisted.
    app1 = _build()
    key1 = app1.config["SECRET_KEY"]
    assert app1.config["FABRICATOR_NEEDS_SETUP"] is True
    resp = app1.test_client().post("/api/auth/setup", json={"password": "operator-pw"})
    assert resp.status_code == 200

    # auth.json holds BOTH the preserved secret_key and the new password_hash.
    data = json.loads((tmp_servers_root / "auth.json").read_text(encoding="utf-8"))
    assert data["secret_key"] == key1
    assert "password_hash" in data

    # "Restart": rebuild the app -> SAME key loaded (sessions survive), and now
    # configured (not setup mode); the persisted password authenticates.
    app2 = _build()
    assert app2.config["SECRET_KEY"] == key1
    assert app2.config["FABRICATOR_NEEDS_SETUP"] is False
    c2 = app2.test_client()
    assert c2.post("/api/auth/login", json={"password": "operator-pw"}).status_code == 200
    assert c2.get("/api/servers").status_code == 200
