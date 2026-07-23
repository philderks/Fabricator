"""`fabricator status` CLI: reachability + server summary.

Regression guard: the old code hit a non-existent /api/status (404), so Flask
looked "up" but the status view only ever printed "no Minecraft data available".
It now probes /api/health and summarises /api/servers.
"""
from unittest.mock import MagicMock

import tools.cli as cli


def _resp(ok=True, json_body=None, status_code=200):
    r = MagicMock()
    r.ok = ok
    r.status_code = status_code
    r.json.return_value = json_body
    return r


def test_collect_status_probes_health_not_status(monkeypatch):
    calls = []

    def fake_get(url, timeout=None):
        calls.append(url)
        if url.endswith("/api/health"):
            return _resp(ok=True, json_body={"healthy": True})
        if url.endswith("/api/servers"):
            return _resp(ok=True, json_body=[
                {"name": "Alpha", "runtime": {"status": "running"}},
                {"name": "Beta", "status": "stopped"},
            ])
        return _resp(ok=False)

    monkeypatch.setattr(cli.requests, "get", fake_get)
    monkeypatch.setattr(cli.subprocess, "run",
                        lambda *a, **k: MagicMock(stdout="active\n"))

    data = cli._collect_status()

    assert any(u.endswith("/api/health") for u in calls)
    assert not any(u.endswith("/api/status") for u in calls)  # the old, 404-ing endpoint
    assert data["flask_up"] is True
    assert data["systemd_state"] == "active"
    assert isinstance(data["servers"], list) and len(data["servers"]) == 2


def test_collect_status_flask_down_when_health_unreachable(monkeypatch):
    def boom(url, timeout=None):
        raise Exception("connection refused")

    monkeypatch.setattr(cli.requests, "get", boom)
    monkeypatch.setattr(cli.subprocess, "run",
                        lambda *a, **k: MagicMock(stdout="inactive\n"))

    data = cli._collect_status()
    assert data["flask_up"] is False
    assert data["servers"] is None


def test_render_status_summarises_running_servers(monkeypatch):
    lines = []
    monkeypatch.setattr(cli.click, "echo", lambda msg="": lines.append(msg))
    monkeypatch.setattr(cli.click, "style", lambda text, **k: text)

    cli._render_status({
        "systemd_state": "active",
        "flask_up": True,
        "servers": [
            {"name": "Alpha", "runtime": {"status": "running"}},
            {"name": "Beta", "status": "stopped"},
        ],
    })

    joined = "\n".join(lines)
    assert "Servers:  1/2 running" in joined
    assert "Alpha" in joined
    assert "no Minecraft data available" not in joined  # the old, misleading message


def test_collect_status_flags_auth_required_on_401(monkeypatch):
    """When auth is enabled (the default), /api/servers returns 401. The
    status must record that distinctly, not lump it in with a generic
    unreadable-list failure."""
    def fake_get(url, timeout=None):
        if url.endswith("/api/health"):
            return _resp(ok=True, json_body={"healthy": True})
        if url.endswith("/api/servers"):
            return _resp(ok=False, status_code=401)
        return _resp(ok=False, status_code=404)

    monkeypatch.setattr(cli.requests, "get", fake_get)
    monkeypatch.setattr(cli.subprocess, "run",
                        lambda *a, **k: MagicMock(stdout="active\n"))

    data = cli._collect_status()

    assert data["flask_up"] is True
    assert data["servers"] is None
    assert data["servers_error"] == "auth_required"


def test_render_status_auth_required_is_honest(monkeypatch):
    """The 401 line states what is true (auth enabled) and where the list is
    (the web panel) — not the misleading 'could not read the server list'."""
    lines = []
    monkeypatch.setattr(cli.click, "echo", lambda msg="": lines.append(msg))
    monkeypatch.setattr(cli.click, "style", lambda text, **k: text)

    cli._render_status({
        "systemd_state": "active",
        "flask_up": True,
        "servers": None,
        "servers_error": "auth_required",
    })

    joined = "\n".join(lines)
    assert "could not read the server list" not in joined
    assert "authentication" in joined.lower()
    assert "web panel" in joined.lower()
