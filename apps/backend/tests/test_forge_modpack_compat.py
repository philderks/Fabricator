"""E3 regression: Forge-tagged Modrinth modpack must not install on a NeoForge server.

Modrinth's loader strings are distinct: ``forge`` vs ``neoforge``. The
existing ``ModrinthClient._resolve_modpack_version`` validates that the
picked version's ``loaders`` array contains the requested loader and
raises ``ModrinthApiError`` on mismatch (route maps to 409, verified in
Phase 3a's Quilt-modpack-compat test).

This test pins the Forge↔NeoForge separation: a user on a NeoForge
server who tries to import a Forge-only modpack must get a clean 409,
never a silent partial install. We mock at ``get_project_versions``
(one layer DOWN from ``_resolve_modpack_version``) so the real
validation path runs end-to-end.
"""
from __future__ import annotations

from unittest.mock import patch


def test_forge_modpack_on_neoforge_server_rejected(client, tmp_servers_root):
    """A modpack tagged loader=forge must not install on a neoforge server."""
    from backend.server import storage
    server = storage.create_server({
        "name": "NeoForgeSrv",
        "version": "1.20.1",
        "loader": "neoforge",
        "port": 25572,
        "installPath": "neoforge-srv",
        "memory": 4,
    })
    server_id = server["id"]

    fake_forge_version = {
        "id": "ver_forgeonly",
        "version_number": "1.0.0",
        "loaders": ["forge"],
        "game_versions": ["1.20.1"],
        "files": [{
            "url": "http://example.invalid/pack.mrpack",
            "filename": "pack.mrpack",
            "primary": True,
        }],
    }

    with patch(
        "backend.modrinth.client.ModrinthClient.get_project",
        return_value={"title": "Example Pack"},
    ), patch(
        "backend.modrinth.client.ModrinthClient.get_project_versions",
        return_value=[fake_forge_version],
    ):
        resp = client.post(
            "/api/modrinth/modpack/example-pack/install",
            json={
                "server_id": server_id,
                "mc_version": "1.20.1",
                "loader": "neoforge",
            },
        )

    assert resp.status_code == 409, (
        f"Expected 409 for loader mismatch, got {resp.status_code}: "
        f"{resp.get_data(as_text=True)}"
    )
    body = resp.get_json()
    text = (body.get("error", "") + " " + body.get("message", "")).lower()
    assert "loader" in text
