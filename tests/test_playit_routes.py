"""Tests for backend.playit.routes — Blueprint endpoints.

Smoke-level: confirms each route is wired, calls into the agent, and returns
the post-action status snapshot (not {"ok": true}). Lifecycle correctness
itself is covered in test_playit_agent.py.
"""
from __future__ import annotations

import threading
from contextlib import contextmanager
from unittest.mock import patch

import pytest


@contextmanager
def _stalled_provisioning():
    """Patch provisioning so it blocks for the duration of the test.

    start() with no binaries present spawns a provisioning thread. Left real it
    would reach out to GitHub; left fast it would race the assertion by
    flipping the status out of "provisioning" before the response is built.
    Blocking pins the snapshot deterministically.
    """
    release_it = threading.Event()

    def _block(*_args, **_kwargs):
        from backend.playit.provision import ProvisionError

        release_it.wait(timeout=5)
        # A clean, expected failure: the thread logs a warning and exits rather
        # than dumping a traceback into the test output.
        raise ProvisionError("stubbed")

    with patch("backend.playit.provision.ensure_binaries", side_effect=_block):
        try:
            yield
        finally:
            release_it.set()


@pytest.fixture
def playit_client(app, monkeypatch, tmp_path):
    """Like the standard `client` fixture but with the agent reset to defaults."""
    monkeypatch.setenv("PLAYIT_RUNTIME_DIR", str(tmp_path))
    import importlib
    from backend.playit import agent as agent_mod
    importlib.reload(agent_mod)
    with agent_mod._lock:
        agent_mod._status        = "stopped"
        agent_mod._tunnels       = []
        agent_mod._tunnels_known = False
        agent_mod._claim_url     = None
        agent_mod._error_reason  = None
        agent_mod._gen           = 0
    return app.test_client()


def test_status_returns_full_snapshot_shape(playit_client):
    """GET /api/playit/status returns the documented daemon-level snapshot."""
    resp = playit_client.get("/api/playit/status")
    assert resp.status_code == 200
    body = resp.get_json()
    assert set(body.keys()) == {
        "status", "claim_url", "error_reason", "binary_trust",
        "tunnels", "tunnels_known",
    }
    assert body["status"] == "stopped"
    assert body["claim_url"] is None
    assert body["error_reason"] is None
    assert body["tunnels"] == []
    assert body["tunnels_known"] is False


def test_start_returns_status_body_not_ok_envelope(playit_client):
    """POST /api/playit/start returns a status snapshot, not {"ok": true}."""
    # No binaries on this dev box — start() hands off to provisioning and says
    # so in-body. ensure_binaries is stubbed so the test never hits GitHub.
    with patch("backend.playit.binary.find_daemon", return_value=None), \
         _stalled_provisioning():
        resp = playit_client.post("/api/playit/start")
    assert resp.status_code == 200, "must be 200; the response BODY conveys the error"
    body = resp.get_json()
    # Body-first contract: frontend branches on these fields, not on HTTP code.
    assert body["status"] == "provisioning"
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
    keys = {"status", "claim_url", "error_reason", "binary_trust",
            "tunnels", "tunnels_known"}
    for route in ("/api/playit/status",):
        body = playit_client.get(route).get_json()
        assert set(body.keys()) == keys, f"GET {route} body keys: {body.keys()}"
    for route in ("/api/playit/start", "/api/playit/stop", "/api/playit/reset"):
        with patch("backend.playit.binary.find_daemon", return_value=None), \
             _stalled_provisioning():
            body = playit_client.post(route).get_json()
        assert set(body.keys()) == keys, f"POST {route} body keys: {body.keys()}"
