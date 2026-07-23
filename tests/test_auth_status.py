"""Status endpoint reports enabled + authenticated + needs_setup + managed."""
from __future__ import annotations


def test_status_enabled_unauthenticated(auth_client):
    assert auth_client.get("/api/auth/status").get_json() == {
        "enabled": True,
        "authenticated": False,
        "needs_setup": False,
        "managed": False,
    }


def test_status_enabled_authenticated(authed_client):
    assert authed_client.get("/api/auth/status").get_json() == {
        "enabled": True,
        "authenticated": True,
        "needs_setup": False,
        "managed": False,
    }


def test_status_setup_mode(setup_client):
    assert setup_client.get("/api/auth/status").get_json() == {
        "enabled": True,
        "authenticated": False,
        "needs_setup": True,
        "managed": False,
    }


def test_status_disabled(client):
    # The default `client` fixture runs with FABRICATOR_DISABLE_AUTH=1.
    assert client.get("/api/auth/status").get_json() == {
        "enabled": False,
        "authenticated": False,
        "needs_setup": False,
        "managed": False,
    }


def test_status_includes_managed_true(tmp_servers_root, monkeypatch):
    """Managed mode surfaces as `managed: True` in the boot status probe.

    Independent of auth: the default temp env disables auth, so the rest of the
    payload stays falsey while `managed` flips on.
    """
    monkeypatch.setenv("FABRICATOR_MANAGED", "1")
    import backend.server.registry as registry_mod

    registry_mod.reset_for_tests()
    from backend.core.app import create_app

    app = create_app()
    app.config["TESTING"] = True
    body = app.test_client().get("/api/auth/status").get_json()
    assert body["managed"] is True
