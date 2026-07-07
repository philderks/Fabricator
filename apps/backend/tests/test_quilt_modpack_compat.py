"""E3 regression: Modrinth modpack loader-string must match the server's loader.

Modrinth uses distinct loader strings: ``fabric`` and ``quilt``. The
existing ``ModrinthClient._resolve_modpack_version`` already validates
that the picked version's ``loaders`` array contains the requested
loader (raises ``ModrinthApiError`` with a loader-mismatch payload).

This test pins that contract for Quilt by mocking one layer DOWN:
``get_project_versions`` returns a Fabric-only version list, so
``_resolve_modpack_version`` runs through its real validation path and
fires its real loader-mismatch response. Mocking
``_resolve_modpack_version`` itself would skip the very check we're
trying to verify.
"""
from __future__ import annotations

from unittest.mock import patch


def test_fabric_modpack_on_quilt_server_rejected(client, tmp_servers_root):
    """A modpack tagged loader=fabric must not install on a quilt server."""
    from backend.server import storage
    server = storage.create_server({
        "name": "QuiltSrv",
        "version": "1.21.4",
        "loader": "quilt",
        "port": 25569,
        "installPath": "quilt-srv",
        "memory": 4,
    })
    server_id = server["id"]

    # One-layer-down mock: get_project_versions is the seam
    # _resolve_modpack_version reads from. Returning a Fabric-only version
    # regardless of the `loaders` arg means:
    #   1) The first call (loaders=["quilt"]) and the fallback call
    #      (loaders=None) both return [fabric_version].
    #   2) _resolve_modpack_version picks the fabric version as "best".
    #   3) Its loader-compat check sees loader='quilt' not in ['fabric']
    #      and raises ModrinthApiError(status=409, ...).
    #   4) The route handler maps the exception to the HTTP response.
    fake_fabric_version = {
        "id": "ver_xyz",
        "version_number": "1.0.0",
        "loaders": ["fabric"],
        "game_versions": ["1.21.4"],
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
        return_value=[fake_fabric_version],
    ):
        resp = client.post(
            "/api/modrinth/modpack/example-pack/install",
            json={
                "server_id": server_id,
                "mc_version": "1.21.4",
                "loader": "quilt",
            },
        )

    assert resp.status_code == 409, (
        f"Expected 409 for loader mismatch, got {resp.status_code}: "
        f"{resp.get_data(as_text=True)}"
    )
    body = resp.get_json()
    # The error must surface the loader-mismatch reason, not a generic
    # "modpack install failed". Specific enough that a user can act on it.
    text = (body.get("error", "") + " " + body.get("message", "")).lower()
    assert "loader" in text
