"""Logout endpoint (protected)."""
from __future__ import annotations


def test_logout_clears_session(authed_client):
    assert authed_client.get("/api/servers").status_code == 200
    resp = authed_client.post("/api/auth/logout")
    assert resp.status_code == 200
    assert resp.get_json() == {"authenticated": False}
    assert authed_client.get("/api/servers").status_code == 401


def test_logout_unauthenticated_is_401(auth_client):
    # logout is NOT in the public allowlist — the gate blocks it without a session.
    assert auth_client.post("/api/auth/logout").status_code == 401
