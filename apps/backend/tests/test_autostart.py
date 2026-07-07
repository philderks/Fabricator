"""Tests for per-server boot auto-start (mode decision + API endpoint)."""
from __future__ import annotations

import pytest

from backend.server import autostart


# ── Decision logic ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("value,expected", [
    ("always", "always"),
    ("never", "never"),
    ("last", "last"),
    ("LAST", "last"),
    ("junk", "never"),
    (None, "never"),
    ("", "never"),
])
def test_normalize_mode(value, expected):
    assert autostart.normalize_mode(value) == expected


@pytest.mark.parametrize("server,expected", [
    # always → start whenever installed (stopped or running)
    ({"status": "stopped", "autoStart": "always"}, True),
    ({"status": "running", "autoStart": "always"}, True),
    # last → only if it was running
    ({"status": "running", "autoStart": "last"}, True),
    ({"status": "stopped", "autoStart": "last"}, False),
    # never → never
    ({"status": "running", "autoStart": "never"}, False),
    # missing field defaults to never
    ({"status": "running"}, False),
    # not-yet-installed states never auto-start, even on "always"
    ({"status": "installing", "autoStart": "always"}, False),
    ({"status": "pending", "autoStart": "always"}, False),
    ({"status": "failed", "autoStart": "last"}, False),
])
def test_should_start(server, expected):
    assert autostart._should_start(server) is expected


def test_autostart_servers_launches_only_targets(monkeypatch):
    """autostart_servers starts exactly the servers whose mode/state qualify."""
    servers = [
        {"id": "a", "status": "stopped", "autoStart": "always", "version": "1.20"},
        {"id": "b", "status": "running", "autoStart": "last", "version": "1.20"},
        {"id": "c", "status": "stopped", "autoStart": "last", "version": "1.20"},
        {"id": "d", "status": "running", "autoStart": "never", "version": "1.20"},
    ]
    monkeypatch.setattr(autostart, "_start_one", lambda s: started.append(s["id"]))
    monkeypatch.setattr(
        "backend.server.storage.get_all_servers", lambda: servers
    )

    started: list[str] = []
    # Run the spawned threads inline so we can assert synchronously.
    real_thread = autostart.threading.Thread

    def _inline_thread(target, args=(), **kwargs):
        target(*args)
        return real_thread(target=lambda: None)

    monkeypatch.setattr(autostart.threading, "Thread", _inline_thread)
    autostart.autostart_servers()

    assert sorted(started) == ["a", "b"]


# ── API endpoint ─────────────────────────────────────────────────────────────

def _make_server(**overrides):
    from backend.server import storage
    return storage.create_server({"name": "t", "version": "1.20", **overrides})


def test_set_autostart_persists(client, tmp_servers_root):
    from backend.server import storage
    server = _make_server()

    resp = client.put(f"/api/servers/{server['id']}/autostart", json={"mode": "always"})
    assert resp.status_code == 200
    assert resp.get_json()["autoStart"] == "always"
    assert storage.get_server(server["id"])["autoStart"] == "always"


def test_set_autostart_rejects_invalid_mode(client, tmp_servers_root):
    server = _make_server()
    resp = client.put(f"/api/servers/{server['id']}/autostart", json={"mode": "sometimes"})
    assert resp.status_code == 400


def test_set_autostart_unknown_server_404(client, tmp_servers_root):
    resp = client.put("/api/servers/srv_doesnotexist/autostart", json={"mode": "never"})
    assert resp.status_code == 404
