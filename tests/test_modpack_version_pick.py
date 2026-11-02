"""Installing a named modpack version, and the loader-build offer (issue #104).

A pack install always took whatever resolved as newest, so updating to a
specific version or rolling back was impossible. `version_id` names the
version; like a pinned mod (#56) it must belong to the project it is installed
under. When the pack pins a loader build the server does not run, the response
carries `loader_change` so the UI can offer the swap.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest


def _make_server(tmp_servers_root, loader="neoforge", **extra):
    from backend.server import storage

    server = storage.create_server({
        "name": "PackSrv", "version": "1.21.1", "loader": loader,
        "port": 25570, "installPath": "pack-srv", **extra,
    })
    (tmp_servers_root / "servers" / "pack-srv").mkdir(parents=True, exist_ok=True)
    return server["id"]


def _version(version_id="vOLD", project_id="PACK", games=("1.21.1",), loaders=("neoforge",)):
    return {
        "id": version_id,
        "project_id": project_id,
        "version_number": "1.2.0",
        "name": "Pack 1.2.0",
        "game_versions": list(games),
        "loaders": list(loaders),
        "files": [{"url": "https://cdn/pack.mrpack", "primary": True, "filename": "pack.mrpack"}],
    }


def _install_result(neoforge="21.1.169"):
    return {
        "files_installed": [], "files_skipped": [], "missing_files": [],
        "uncertain_mod_files": [], "cleaned_paths": [],
        "dependencies": {"minecraft": "1.21.1", "neoforge": neoforge},
    }


def _post(client, server_id, version, *, builds=("21.1.169", "21.1.200"), result=None):
    with patch("backend.modrinth.client.ModrinthClient.get_project", return_value={"id": "PACK", "title": "Pack"}), \
         patch("backend.modrinth.client.ModrinthClient.get_version", return_value=version), \
         patch("backend.modrinth.client.ModrinthClient._download_mrpack"), \
         patch("backend.modrinth.client.ModrinthClient.install_mrpack_archive",
               return_value=result or _install_result()) as install, \
         patch("backend.server.installer.neoforge.NeoForgeInstaller.get_available_versions",
               return_value=[{"version": b} for b in builds]):
        resp = client.post("/api/modrinth/modpack/PACK/install", json={
            "server_id": server_id, "mc_version": "1.21.1", "loader": "neoforge",
            "version_id": version["id"], "create_backup": False,
        })
    return resp, install


def test_named_version_is_installed_and_recorded(client, tmp_servers_root):
    from backend.server import storage

    server_id = _make_server(tmp_servers_root, loaderVersion="21.1.169")
    resp, install = _post(client, server_id, _version())

    assert resp.status_code == 200, resp.get_json()
    assert install.called
    assert storage.get_server(server_id)["modpack"]["versionId"] == "vOLD"
    assert "loader_change" not in resp.get_json()


def test_version_of_another_project_is_refused(client, tmp_servers_root):
    server_id = _make_server(tmp_servers_root)
    resp, install = _post(client, server_id, _version(project_id="OTHER"))

    assert resp.status_code == 400
    assert not install.called


def test_version_for_another_minecraft_is_refused(client, tmp_servers_root):
    server_id = _make_server(tmp_servers_root)
    resp, install = _post(client, server_id, _version(games=("1.20.1",)))

    assert resp.status_code == 409
    assert not install.called


@pytest.mark.parametrize("current", ["21.1.169", None])
def test_loader_change_offered_when_pack_pins_another_build(client, tmp_servers_root, current):
    extra = {"loaderVersion": current} if current else {}
    server_id = _make_server(tmp_servers_root, **extra)
    resp, _ = _post(client, server_id, _version(), result=_install_result("21.1.200"))

    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["loader_change"] == {
        "loader": "neoforge", "current": current, "required": "21.1.200",
    }


def test_no_loader_change_for_a_build_the_installer_cannot_supply(client, tmp_servers_root):
    server_id = _make_server(tmp_servers_root, loaderVersion="21.1.169")
    resp, _ = _post(client, server_id, _version(), builds=("21.1.169",),
                    result=_install_result("21.1.999"))

    assert resp.status_code == 200
    assert "loader_change" not in resp.get_json()
