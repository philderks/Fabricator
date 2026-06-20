"""Login endpoint."""
from __future__ import annotations

from backend.auth import service

PW = "s3cret-test-pw"


def test_login_success_sets_session(auth_client):
    resp = auth_client.post("/api/auth/login", json={"password": PW})
    assert resp.status_code == 200
    assert resp.get_json() == {"authenticated": True}
    assert auth_client.get("/api/servers").status_code == 200


def test_login_wrong_password_401_no_session_no_leak(auth_client, monkeypatch):
    import backend.auth.routes as routes
    monkeypatch.setattr(routes, "LOGIN_FAILURE_DELAY_SECONDS", 0)

    resp = auth_client.post("/api/auth/login", json={"password": "nope"})
    assert resp.status_code == 401
    assert resp.get_json() == {"error": "invalid credentials"}
    # The configured hash must never appear in the response body.
    assert service.get_password_hash() not in resp.get_data(as_text=True)
    # Still locked out.
    assert auth_client.get("/api/servers").status_code == 401


def test_login_missing_password_400(auth_client):
    assert auth_client.post("/api/auth/login", json={}).status_code == 400


def test_login_non_json_400(auth_client):
    resp = auth_client.post(
        "/api/auth/login", data="not json", content_type="application/json"
    )
    assert resp.status_code == 400
