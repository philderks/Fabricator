"""Status endpoint reports enabled + authenticated."""
from __future__ import annotations


def test_status_enabled_unauthenticated(auth_client):
    assert auth_client.get("/api/auth/status").get_json() == {
        "enabled": True,
        "authenticated": False,
    }


def test_status_enabled_authenticated(authed_client):
    assert authed_client.get("/api/auth/status").get_json() == {
        "enabled": True,
        "authenticated": True,
    }


def test_status_disabled(client):
    # The default `client` fixture runs with FABRICATOR_DISABLE_AUTH=1.
    assert client.get("/api/auth/status").get_json() == {
        "enabled": False,
        "authenticated": False,
    }
