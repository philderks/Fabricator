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
    from backend.core.version import get_app_version

    assert authed_client.get("/api/auth/status").get_json() == {
        "enabled": True,
        "authenticated": True,
        "needs_setup": False,
        "managed": False,
        # Only a caller that has proved itself sees the version.
        "panel_version": get_app_version(),
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


def test_status_includes_panel_version_for_a_token_caller(auth_client):
    """The MCP client reads this with a token, so the token path must carry it."""
    from backend.auth import service
    from backend.core.version import get_app_version

    service.set_mcp_enabled(True)
    token = service.create_token("t", "read")["token"]

    body = auth_client.get(
        "/api/auth/status", headers={"Authorization": f"Bearer {token}"}
    ).get_json()

    assert body["panel_version"] == get_app_version()


def test_status_omits_panel_version_for_an_unauthenticated_caller(auth_client):
    """The route answers without a credential, so the version is not free to take."""
    body = auth_client.get("/api/auth/status").get_json()
    assert "panel_version" not in body


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
