"""The central before_request auth gate."""
from __future__ import annotations


def test_protected_route_401_without_session(auth_client):
    resp = auth_client.get("/api/servers")
    assert resp.status_code == 401
    assert resp.get_json()["error"] == "authentication required"


def test_protected_route_200_with_session(authed_client):
    assert authed_client.get("/api/servers").status_code == 200


def test_options_preflight_passes(auth_client):
    resp = auth_client.open("/api/servers", method="OPTIONS")
    assert resp.status_code != 401


def test_public_endpoints_reachable_without_session(auth_client):
    assert auth_client.get("/api/auth/status").status_code == 200
    assert auth_client.get("/api/health").status_code == 200
    # login is public; an empty body is a 400 (validation), never the gate's 401.
    assert auth_client.post("/api/auth/login", json={}).status_code == 400


def test_non_api_path_not_gated(auth_client):
    # SPA catch-all serves index.html or 503 when unbuilt — never the gate 401.
    assert auth_client.get("/").status_code != 401
