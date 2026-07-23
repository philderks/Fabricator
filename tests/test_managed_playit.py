"""C4 — managed playit gate.

Managed-on: POST /api/playit/start and /reset are 403 (stop stays allowed), and
agent.start() hard-returns before persisting enabled-state so neither an HTTP
call nor the run.py boot re-arm can bring the tunnel up. All tests are
daemon-free (no real playit agent is exercised) so they pass on the Windows
stand where the playit daemon is unsupported.
"""
from __future__ import annotations


def test_managed_start_route_returns_403(client, monkeypatch):
    monkeypatch.setenv("FABRICATOR_MANAGED", "1")
    # 403 returns before agent.start() is touched — no daemon.
    assert client.post("/api/playit/start").status_code == 403


def test_managed_reset_route_returns_403(client, monkeypatch):
    monkeypatch.setenv("FABRICATOR_MANAGED", "1")
    assert client.post("/api/playit/reset").status_code == 403


def test_managed_stop_route_is_allowed(client, monkeypatch):
    monkeypatch.setenv("FABRICATOR_MANAGED", "1")
    import backend.playit.routes as pr

    monkeypatch.setattr(pr.agent, "stop", lambda: None)
    monkeypatch.setattr(pr.agent, "get_status", lambda: {"status": "stopped"})
    assert client.post("/api/playit/stop").status_code != 403


def test_unmanaged_start_route_not_blocked(client, monkeypatch):
    monkeypatch.delenv("FABRICATOR_MANAGED", raising=False)
    import backend.playit.routes as pr

    monkeypatch.setattr(pr.agent, "start", lambda: None)
    monkeypatch.setattr(pr.agent, "get_status", lambda: {"status": "stopped"})
    assert client.post("/api/playit/start").status_code != 403


def test_managed_agent_start_does_not_persist_enabled(monkeypatch):
    """The core guarantee: under managed, agent.start() returns before
    set_enabled(True), so the persisted enabled-state can never re-arm the
    run.py boot auto-start."""
    import backend.playit.agent as agent
    from backend.utils import platform as platform_utils

    monkeypatch.setenv("FABRICATOR_MANAGED", "1")
    # Bypass the Windows early-return so the managed branch is actually reached.
    monkeypatch.setattr(platform_utils, "is_windows", lambda: False)
    calls = []
    monkeypatch.setattr(agent, "set_enabled", lambda enabled: calls.append(enabled))

    agent.start()

    assert calls == []
