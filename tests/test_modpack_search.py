"""Tests for the strict modpack search route and the install-time
compatibility error messages.

Pins two pieces of contract:

1. ``GET /api/modrinth/modpacks/search`` is *strict*: when the upstream
   strict-filtered query returns no hits, the route does NOT silently
   re-query without ``mc_version`` and does NOT decorate the response
   with ``version_filter_fallback``. The empty result is returned
   verbatim so the FE can render an honest "no compatible modpacks"
   empty state.

2. ``ModrinthClient._resolve_modpack_version`` raises a 409 with a
   user-actionable message (mentions both the modpack's MC versions and
   the requested MC version, plus next-step phrasing) AND keeps the
   structured ``details`` dict that the FE / other clients may parse.

No real HTTP calls — the underlying ``ModrinthClient`` methods are
monkeypatched.
"""
from __future__ import annotations

import importlib

import pytest


def _client_module():
    """Always grab the live ``backend.modrinth.client`` module.

    test_app_factory.py wipes backend.* from sys.modules between tests,
    so a top-level import would bind a stale class object.
    """
    return importlib.import_module("backend.modrinth.client")


def test_search_returns_empty_when_strict_filter_misses(client, monkeypatch):
    """Strict search with 0 hits returns the empty result as-is.

    No fallback re-query, no ``version_filter_fallback`` flag.
    """
    # Look up the routes module via importlib so we always grab the same
    # module instance the live Flask app holds — test_app_factory.py wipes
    # backend.* from sys.modules between tests, so a top-level import of
    # this module would bind a stale reference.
    modrinth_routes = importlib.import_module("backend.modrinth.routes")

    calls: list[dict] = []

    def fake_search_modpacks(**kwargs):
        calls.append(kwargs)
        return {"hits": [], "total_hits": 0, "limit": kwargs.get("limit", 20), "offset": 0}

    monkeypatch.setattr(
        modrinth_routes.modrinth_client,
        "search_modpacks",
        fake_search_modpacks,
    )

    resp = client.get(
        "/api/modrinth/modpacks/search",
        query_string={"query": "nope", "mc_version": "1.21", "loader": "fabric"},
    )

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["hits"] == []
    assert body["total_hits"] == 0
    # Proves the fallback was deleted, not just gated.
    assert "version_filter_fallback" not in body
    # And the underlying client was called exactly once — no fallback retry.
    assert len(calls) == 1
    assert calls[0]["mc_version"] == "1.21"


def test_install_compat_error_message_is_actionable(monkeypatch):
    """409 mc-version mismatch has both versions + actionable phrasing.

    The structured ``details`` dict contract is preserved for callers
    that parse it programmatically.
    """
    client_mod = _client_module()
    mp_client = client_mod.ModrinthClient()

    # Mocked upstream: project has one version, but for a different MC.
    def fake_get_project_versions(self, project_id, loaders=None, game_versions=None, featured=None):
        return [{
            "id": "vABC",
            "version_number": "1.0.0",
            "version_type": "release",
            "date_published": "2024-01-01T00:00:00Z",
            "game_versions": ["1.20.1"],
            "loaders": ["fabric"],
            "files": [],
        }]

    monkeypatch.setattr(client_mod.ModrinthClient, "get_project_versions", fake_get_project_versions)

    with pytest.raises(client_mod.ModrinthApiError) as excinfo:
        mp_client._resolve_modpack_version(
            project_id="proj",
            mc_version="1.21",
            loader="fabric",
        )

    err = excinfo.value
    assert err.status_code == 409

    msg = str(err)
    # Mentions BOTH the requested MC and the modpack's MC.
    assert "1.21" in msg
    assert "1.20.1" in msg
    # User-actionable phrasing — exact phrase the implementation uses.
    assert "Pick a different modpack" in msg

    # Machine-readable details contract preserved.
    assert err.details.get("requested_mc_version") == "1.21"
    assert err.details.get("modpack_game_versions") == ["1.20.1"]


def test_install_loader_compat_error_message_is_actionable(monkeypatch):
    """409 loader mismatch has both loaders + actionable phrasing.

    Same shape as the mc-version test, but for the loader path.
    """
    client_mod = _client_module()
    mp_client = client_mod.ModrinthClient()

    # Mocked upstream: project has one version, MC matches, but loader differs.
    def fake_get_project_versions(self, project_id, loaders=None, game_versions=None, featured=None):
        return [{
            "id": "vABC",
            "version_number": "1.0.0",
            "version_type": "release",
            "date_published": "2024-01-01T00:00:00Z",
            "game_versions": ["1.21"],
            "loaders": ["forge"],
            "files": [],
        }]

    monkeypatch.setattr(client_mod.ModrinthClient, "get_project_versions", fake_get_project_versions)

    with pytest.raises(client_mod.ModrinthApiError) as excinfo:
        mp_client._resolve_modpack_version(
            project_id="proj",
            mc_version="1.21",
            loader="fabric",
        )

    err = excinfo.value
    assert err.status_code == 409

    msg = str(err)
    # Mentions BOTH loaders.
    assert "fabric" in msg
    assert "forge" in msg
    # User-actionable phrasing — exact phrase the implementation uses.
    assert "Pick a different modpack" in msg

    # Machine-readable details contract preserved.
    assert err.details.get("requested_loader") == "fabric"
    assert err.details.get("modpack_loaders") == ["forge"]
