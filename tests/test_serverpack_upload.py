"""Installing a modpack's server files zip to change its version (#104).

CurseForge-only packs (All the Mods and friends) can't come through Modrinth,
but publish a server pack per release. Uploading one goes through the same
upload/install routes as a .mrpack.
"""
from __future__ import annotations

import importlib
import zipfile
from pathlib import Path

import pytest

from backend.modrinth import mrpack, serverpack


@pytest.fixture(autouse=True)
def _fresh_modules():
    # Same idiom as tests/test_mrpack_import.py: rebind after module purges.
    global mrpack, serverpack
    mrpack = importlib.import_module("backend.modrinth.mrpack")
    serverpack = importlib.import_module("backend.modrinth.serverpack")
    mrpack.reset_for_tests()
    yield
    mrpack.reset_for_tests()


def make_zip(tmp_path: Path, files: dict, name="ServerFiles-2.4.zip") -> Path:
    path = tmp_path / name
    with zipfile.ZipFile(path, "w") as zf:
        for arcname, content in files.items():
            zf.writestr(arcname, content)
    return path


ATM_STYLE = {
    "ServerFiles-2.4/mods/create.jar": b"jar",
    "ServerFiles-2.4/config/create-common.toml": "a = 1",
    "ServerFiles-2.4/kubejs/server_scripts/x.js": "//",
    "ServerFiles-2.4/startserver.sh": "#!/bin/sh\nNEOFORGE_VERSION=21.1.80\n",
    "ServerFiles-2.4/server.properties": "motd=pack default",
    "ServerFiles-2.4/eula.txt": "eula=false",
    "ServerFiles-2.4/world/level.dat": b"pack world",
}


# ---------------------------------------------------------------------------
# describe
# ---------------------------------------------------------------------------

def test_describe_reads_a_wrapped_pack_and_its_script_loader(tmp_path):
    summary = serverpack.describe(make_zip(tmp_path, ATM_STYLE), "ServerFiles-2.4.zip")

    assert summary["kind"] == "serverpack"
    assert summary["root"] == "ServerFiles-2.4/"
    assert summary["version"] == "2.4"
    assert summary["loader"] == "neoforge"
    assert summary["loader_version"] == "21.1.80"
    assert summary["minecraft_version"] == "1.21.1"
    assert summary["dependencies"] == {"minecraft": "1.21.1", "neoforge": "21.1.80"}
    assert summary["file_count"] == 1


@pytest.mark.parametrize("files, expected", [
    ({"forge-1.20.1-47.2.0-installer.jar": b""}, ("forge", "47.2.0", "1.20.1")),
    ({"neoforge-21.1.77-installer.jar": b""}, ("neoforge", "21.1.77", "1.21.1")),
    ({"variables.txt": "MINECRAFT_VERSION=1.20.1\nMODLOADER=Fabric\nMODLOADER_VERSION=0.15.7\n"},
     ("fabric", "0.15.7", "1.20.1")),
    ({"start.bat": "set FORGE_VERSION=1.20.1-47.3.0\r\n"}, ("forge", "47.3.0", "1.20.1")),
    ({"libraries/net/neoforged/neoforge/21.1.80/x.jar": b""}, ("neoforge", "21.1.80", "1.21.1")),
    ({}, ("", "", "")),
])
def test_describe_detects_the_loader(tmp_path, files, expected):
    pack = make_zip(tmp_path, {"mods/a.jar": b"", **files})

    summary = serverpack.describe(pack, "pack.zip")

    assert (summary["loader"], summary["loader_version"], summary["minecraft_version"]) == expected


def test_describe_rejects_a_curseforge_client_export(tmp_path):
    pack = make_zip(tmp_path, {"manifest.json": "{}", "overrides/config/a.toml": ""})

    with pytest.raises(mrpack.InvalidMrpackError, match="Server Files"):
        serverpack.describe(pack, "pack.zip")


def test_describe_rejects_a_zip_without_mods(tmp_path):
    with pytest.raises(mrpack.InvalidMrpackError, match="server pack"):
        serverpack.describe(make_zip(tmp_path, {"readme.txt": "hi"}), "pack.zip")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

def _make_server(app, tmp_servers_root, *, version="1.21.1", loader="neoforge", path="pack-target"):
    from backend.server import storage

    with app.app_context():
        server = storage.create_server({
            "name": path, "version": version, "loader": loader,
            "port": 25598, "installPath": path,
        })
    root = tmp_servers_root / "servers" / path
    root.mkdir(parents=True, exist_ok=True)
    return server["id"], root


def _upload(client, pack_path, filename="ServerFiles-2.4.zip"):
    return client.post(
        f"/api/modrinth/modpack/upload?filename={filename}",
        data=pack_path.read_bytes(),
        content_type="application/octet-stream",
    )


def test_upload_stages_a_server_pack(client, tmp_path):
    response = _upload(client, make_zip(tmp_path, ATM_STYLE))

    assert response.status_code == 201
    body = response.get_json()
    assert body["kind"] == "serverpack"
    assert body["loader"] == "neoforge"
    assert mrpack.get(body["upload_id"]) is not None


def test_upload_explains_a_zip_that_is_neither_kind(client, tmp_path):
    response = _upload(client, make_zip(tmp_path, {"readme.txt": "hi"}))

    assert response.status_code == 400
    assert "server pack" in response.get_json()["error"]
    assert list(mrpack.staging_dir().glob("mrpack-*.mrpack")) == []


def test_install_swaps_pack_content_and_keeps_the_server_state(
    app, client, tmp_servers_root, tmp_path, monkeypatch
):
    from backend.modrinth import routes as modrinth_routes
    from backend.server import storage

    server_id, root = _make_server(app, tmp_servers_root)
    (root / "mods").mkdir()
    (root / "mods" / "old-version.jar").write_bytes(b"old")
    (root / "world").mkdir()
    (root / "world" / "level.dat").write_bytes(b"my world")
    (root / "server.properties").write_text("motd=mine")
    with app.app_context():
        storage.update_server(server_id, {"loaderVersion": "21.1.60"})
    monkeypatch.setattr(modrinth_routes, "loader_build_available", lambda *a: True)
    upload_id = _upload(client, make_zip(tmp_path, ATM_STYLE)).get_json()["upload_id"]

    response = client.post(
        f"/api/modrinth/modpack/upload/{upload_id}/install",
        json={"server_id": server_id, "create_backup": False},
    )

    assert response.status_code == 200, response.get_json()
    assert not (root / "mods" / "old-version.jar").exists()
    assert (root / "mods" / "create.jar").read_bytes() == b"jar"
    assert (root / "kubejs" / "server_scripts" / "x.js").is_file()
    assert (root / "world" / "level.dat").read_bytes() == b"my world"
    assert (root / "server.properties").read_text() == "motd=mine"
    assert not (root / "startserver.sh").exists()
    assert response.get_json()["loader_change"] == {
        "loader": "neoforge", "current": "21.1.60", "required": "21.1.80",
    }
    with app.app_context():
        recorded = storage.get_server(server_id)["modpack"]
    assert recorded["name"] == "ServerFiles-2.4"
    assert recorded["version"] == "2.4"
    assert recorded["source"] == "upload"


def test_install_never_writes_outside_the_server(app, client, tmp_servers_root, tmp_path):
    server_id, root = _make_server(app, tmp_servers_root)
    pack = make_zip(tmp_path, {"mods/a.jar": b"", "mods/../../escape.txt": "x"})
    upload_id = _upload(client, pack).get_json()["upload_id"]

    response = client.post(
        f"/api/modrinth/modpack/upload/{upload_id}/install",
        json={"server_id": server_id, "create_backup": False},
    )

    assert response.status_code == 200
    assert not (root.parent / "escape.txt").exists()
    assert (root / "mods" / "a.jar").is_file()


def test_server_creation_installs_a_staged_server_pack(tmp_path):
    """The create flow installs through backend.modrinth.pending, not the
    upload route; it must not read a server pack as a .mrpack."""
    from backend.modrinth import pending
    from backend.modrinth.client import ModrinthClient

    archive = make_zip(tmp_path, ATM_STYLE)
    staged = mrpack.stage(
        archive, filename=archive.name, size_bytes=archive.stat().st_size,
        summary=serverpack.describe(archive, archive.name),
    )
    intent = {"source": "upload", "upload_id": staged.upload_id}
    root = tmp_path / "server"
    root.mkdir()

    prepared = pending.prepare(ModrinthClient(), intent)
    result = pending.install_prepared(ModrinthClient(), prepared, intent, root)

    assert prepared.loader_version == "21.1.80"
    assert (root / "mods" / "create.jar").is_file()
    assert not (root / "world").exists()
    assert pending.modpack_record(result)["name"] == "ServerFiles-2.4"
