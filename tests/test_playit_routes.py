"""Tests for backend.playit.routes — Blueprint endpoints.

Smoke-level: confirms each route is wired, calls into the agent, and returns
the post-action status snapshot (not {"ok": true}). Lifecycle correctness
itself is covered in test_playit_agent.py.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest


@pytest.fixture
def playit_client(app, monkeypatch, tmp_path):
    """Like the standard `client` fixture but with the agent reset to defaults."""
    monkeypatch.setenv("PLAYIT_RUNTIME_DIR", str(tmp_path))
    import importlib
    from backend.playit import agent as agent_mod
    importlib.reload(agent_mod)
    with agent_mod._lock:
        agent_mod._status        = "stopped"
        agent_mod._address       = None
        agent_mod._claim_url     = None
        agent_mod._error_reason  = None
        agent_mod._gen           = 0
    return app.test_client()


def test_status_returns_full_snapshot_shape(playit_client):
    """GET /api/playit/status returns all five documented fields."""
    resp = playit_client.get("/api/playit/status")
    assert resp.status_code == 200
    body = resp.get_json()
    assert set(body.keys()) == {
        "status", "address", "claim_url", "error_reason", "binary_verified"
    }
    assert body["status"] == "stopped"
    assert body["address"] is None
    assert body["claim_url"] is None
    assert body["error_reason"] is None


def test_start_returns_status_body_not_ok_envelope(playit_client):
    """POST /api/playit/start returns a status snapshot, not {"ok": true}."""
    # No binaries on this dev box — start() should surface an error in-body.
    with patch("backend.playit.binary.find_daemon", return_value=None):
        resp = playit_client.post("/api/playit/start")
    assert resp.status_code == 200, "must be 200; the response BODY conveys the error"
    body = resp.get_json()
    # Body-first contract: frontend branches on these fields, not on HTTP code.
    assert body["status"] == "error"
    assert "daemon binary not found" in (body["error_reason"] or "")
    # The legacy `{"ok": true}` shape must be gone.
    assert "ok" not in body


def test_stop_returns_status_body(playit_client):
    resp = playit_client.post("/api/playit/stop")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "stopped"


def test_reset_returns_status_body(playit_client, tmp_path):
    secret_file = tmp_path / "playit.toml"
    secret_file.write_text("dummy")

    resp = playit_client.post("/api/playit/reset")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "stopped"
    assert not secret_file.exists()


def test_start_stop_roundtrip_shape(playit_client):
    """All endpoints return the same body shape (frontend uses one parser)."""
    keys = {"status", "address", "claim_url", "error_reason", "binary_verified"}
    for route in ("/api/playit/status",):
        body = playit_client.get(route).get_json()
        assert set(body.keys()) == keys, f"GET {route} body keys: {body.keys()}"
    for route in ("/api/playit/start", "/api/playit/stop", "/api/playit/reset"):
        with patch("backend.playit.binary.find_daemon", return_value=None):
            body = playit_client.post(route).get_json()
        assert set(body.keys()) == keys, f"POST {route} body keys: {body.keys()}"
