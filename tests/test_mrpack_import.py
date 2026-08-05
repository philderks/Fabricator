"""Importing a user-exported Modrinth modpack archive (issue #53).

A .mrpack the user exported from the Modrinth app has no project id and no
upstream version to resolve, so everything Fabricator needs — the Minecraft
version, the loader, the file list — has to come out of the archive itself.
The pack is staged on upload rather than installed, because during server
creation the server it will land on does not exist yet.

Covers the three layers that adds: reading and validating an index
(``backend.modrinth.mrpack``), installing from an on-disk archive
(``ModrinthClient.install_mrpack_archive``), and the upload/install/discard
routes — including the checks that make an uploaded archive safe to accept.
"""
from __future__ import annotations

import importlib
import json
import zipfile
from pathlib import Path

import pytest

from backend.modrinth import mrpack
from backend.modrinth.client import ModrinthApiError, ModrinthClient


@pytest.fixture(autouse=True)
def _fresh_modules():
    """Re-bind against what sys.modules holds NOW, and clear staging.

    test_app_factory.py purges every ``backend.*`` module, so an import-time
    binding can end up pointing at a different module object than the routes
    use — and the staging registry is module state, so this file would then
    be inspecting a registry nobody writes to. Same idiom as
    tests/test_modrinth_pinned_version.py.
    """
    global mrpack, ModrinthApiError, ModrinthClient
    mrpack = importlib.import_module("backend.modrinth.mrpack")
    client_module = importlib.import_module("backend.modrinth.client")
    ModrinthApiError = client_module.ModrinthApiError
    ModrinthClient = client_module.ModrinthClient

    mrpack.reset_for_tests()
    yield
    mrpack.reset_for_tests()


def make_index(
    *,
    name="Test Pack",
    version_id="1.2.3",
    minecraft="1.20.1",
    loader_key="fabric-loader",
    loader_version="0.15.7",
    files=None,
    game="minecraft",
):
    index = {
        "formatVersion": 1,
        "game": game,
        "versionId": version_id,
        "name": name,
        "summary": "A pack for tests",
        "files": files if files is not None else [],
        "dependencies": {"minecraft": minecraft},
    }
    if loader_key:
        index["dependencies"][loader_key] = loader_version
    return index


def make_mrpack(tmp_path: Path, index=None, overrides=None, name="pack.mrpack", extra=None) -> Path:
    """Build a synthetic .mrpack. ``overrides`` maps arcname -> content."""
    path = tmp_path / name
    with zipfile.ZipFile(path, "w") as zf:
        if index is not None:
            zf.writestr("modrinth.index.json", json.dumps(index))
        for arcname, content in (overrides or {}).items():
            zf.writestr(arcname, content)
        for arcname, content in (extra or {}).items():
            zf.writestr(arcname, content)
    return path


def mod_entry(path="mods/example.jar", *, env=None, url="https://cdn.example/mod.jar"):
    entry = {"path": path, "downloads": [url], "fileSize": 10}
    if env is not None:
        entry["env"] = env
    return entry


# ---------------------------------------------------------------------------
# Index reading + validation
# ---------------------------------------------------------------------------

def test_read_index_returns_the_manifest(tmp_path):
    path = make_mrpack(tmp_path, make_index())
    assert mrpack.read_index(path)["name"] == "Test Pack"


def test_read_index_rejects_a_file_that_is_not_a_zip(tmp_path):
    path = tmp_path / "not-a-pack.mrpack"
    path.write_bytes(b"this is a jpeg, actually")
    with pytest.raises(mrpack.InvalidMrpackError, match="not a readable .mrpack"):
        mrpack.read_index(path)


def test_read_index_rejects_a_zip_without_an_index(tmp_path):
    """A plain zip of a mods folder is the likeliest wrong file to pick."""
    path = make_mrpack(tmp_path, index=None, overrides={"mods/a.jar": "x"})
    with pytest.raises(mrpack.InvalidMrpackError, match="modrinth.index.json"):
        mrpack.read_index(path)


def test_read_index_rejects_malformed_json(tmp_path):
    path = tmp_path / "bad.mrpack"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("modrinth.index.json", "{not json")
    with pytest.raises(mrpack.InvalidMrpackError, match="not valid JSON"):
        mrpack.read_index(path)


def test_read_index_rejects_a_pack_for_another_game(tmp_path):
    path = make_mrpack(tmp_path, make_index(game="terraria"))
    with pytest.raises(mrpack.InvalidMrpackError, match="not Minecraft"):
        mrpack.read_index(path)


def test_read_index_rejects_a_malformed_files_list(tmp_path):
    index = make_index()
    index["files"] = "everything"
    path = make_mrpack(tmp_path, index)
    with pytest.raises(mrpack.InvalidMrpackError, match="malformed 'files'"):
        mrpack.read_index(path)


def test_read_index_rejects_a_zip_bomb(tmp_path, monkeypatch):
    """The cap is read off the central directory, before anything expands."""
    monkeypatch.setenv("FABRICATOR_MAX_MRPACK_EXTRACTED_BYTES", "1024")
    path = make_mrpack(
        tmp_path, make_index(), overrides={"overrides/config/big.cfg": "A" * 5000}
    )
    with pytest.raises(mrpack.InvalidMrpackError, match="expands to more than"):
        mrpack.read_index(path)


# ---------------------------------------------------------------------------
# describe()
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("key,expected", [
    ("fabric-loader", "fabric"),
    ("quilt-loader", "quilt"),
    ("neoforge", "neoforge"),
    ("forge", "forge"),
])
def test_describe_maps_each_loader_dependency(key, expected):
    summary = mrpack.describe(make_index(loader_key=key))
    assert summary["loader"] == expected
    assert summary["loader_version"] == "0.15.7"


def test_describe_prefers_quilt_when_a_pack_lists_both_loaders():
    """Quilt runs Fabric mods, so a Quilt pack may declare fabric-loader too —
    but it is the Quilt entry that describes the pack."""
    index = make_index(loader_key="quilt-loader")
    index["dependencies"]["fabric-loader"] = "0.15.7"
    assert mrpack.describe(index)["loader"] == "quilt"


def test_describe_reports_the_minecraft_version_and_file_counts():
    index = make_index(files=[
        mod_entry("mods/a.jar"),
        mod_entry("mods/b.jar", env={"client": "required", "server": "unsupported"}),
    ])
    summary = mrpack.describe(index)
    assert summary["minecraft_version"] == "1.20.1"
    assert summary["file_count"] == 2
    assert summary["client_only_count"] == 1


def test_describe_leaves_undeclared_fields_empty():
    """A pack with no loader dependency is not an error here — the caller
    decides whether it can still be installed."""
    summary = mrpack.describe(make_index(loader_key=None))
    assert summary["loader"] == ""
    assert summary["minecraft_version"] == "1.20.1"


def test_describe_flags_override_trees(tmp_path):
    path = make_mrpack(tmp_path, make_index(), overrides={
        "overrides/config/foo.toml": "a=1",
        "server-overrides/config/bar.toml": "b=2",
    })
    summary = mrpack.describe(mrpack.read_index(path), path)
    assert summary["has_overrides"] is True
    assert summary["has_server_overrides"] is True


# ---------------------------------------------------------------------------
# compare_with_server()
# ---------------------------------------------------------------------------

def test_compare_with_server_passes_a_matching_pack():
    summary = mrpack.describe(make_index())
    assert mrpack.compare_with_server(
        summary, {"version": "1.20.1", "loader": "fabric"}
    ) is None


def test_compare_with_server_reports_both_kinds_of_mismatch():
    summary = mrpack.describe(make_index(minecraft="1.21.4", loader_key="neoforge"))
    mismatch = mrpack.compare_with_server(
        summary, {"version": "1.20.1", "loader": "fabric"}
    )
    assert mismatch["pack_mc_version"] == "1.21.4"
    assert mismatch["server_loader"] == "fabric"
    assert len(mismatch["reasons"]) == 2


def test_compare_with_server_ignores_what_the_pack_does_not_declare():
    """A pack that names no loader cannot contradict the server's."""
    summary = mrpack.describe(make_index(loader_key=None))
    assert mrpack.compare_with_server(
        summary, {"version": "1.20.1", "loader": "fabric"}
    ) is None


# ---------------------------------------------------------------------------
# Staging store
# ---------------------------------------------------------------------------

def _stage(tmp_path, name="pack.mrpack"):
    path = make_mrpack(tmp_path, make_index(), name=name)
    return mrpack.stage(path, filename=name, size_bytes=path.stat().st_size, summary={})


def test_stage_then_get_returns_the_same_pack(tmp_path):
    staged = _stage(tmp_path)
    assert mrpack.get(staged.upload_id).path == staged.path


def test_get_rejects_an_unknown_id(tmp_path):
    """Ids are looked up in the registry, never joined onto a directory, so a
    caller cannot reach a path of their choosing through one."""
    _stage(tmp_path)
    assert mrpack.get("../../etc/passwd") is None
    assert mrpack.get("") is None


def test_get_forgets_a_pack_whose_file_vanished(tmp_path):
    staged = _stage(tmp_path)
    staged.path.unlink()
    assert mrpack.get(staged.upload_id) is None


def test_discard_removes_the_file(tmp_path):
    staged = _stage(tmp_path)
    assert mrpack.discard(staged.upload_id) is True
    assert not staged.path.exists()
    assert mrpack.discard(staged.upload_id) is False


def test_sweep_expired_drops_stale_packs_but_keeps_fresh_ones(tmp_path, tmp_servers_root):
    stale = _stage(tmp_path, "stale.mrpack")
    fresh = _stage(tmp_path, "fresh.mrpack")
    stale.created_at -= mrpack.STAGING_TTL_SECONDS + 60

    assert mrpack.sweep_expired() == 1
    assert not stale.path.exists()
    assert fresh.path.exists()


def test_sweep_expired_removes_orphans_left_by_a_restart(tmp_path, tmp_servers_root):
    """The registry is in memory: a restart between upload and install would
    otherwise leave an archive on disk that nothing remembers."""
    staging = mrpack.staging_dir()
    staging.mkdir(parents=True, exist_ok=True)
    orphan = staging / "mrpack-deadbeef.mrpack"
    orphan.write_bytes(b"stale")
    import os
    old = 1_000_000.0
    os.utime(orphan, (old, old))

    assert mrpack.sweep_expired() == 1
    assert not orphan.exists()


# ---------------------------------------------------------------------------
# install_mrpack_archive()
# ---------------------------------------------------------------------------

def _client():
    from backend.modrinth.ratelimit import RateLimiter
    return ModrinthClient(limiter=RateLimiter(capacity=1000, window_seconds=1.0))


def _fake_download(monkeypatch, client, *, body=b"jar-bytes"):
    """Write a file instead of fetching one, and skip the reachability probe."""
    def _download_and_verify(url, target, hashes, error_context):
        Path(target).write_bytes(body)

    monkeypatch.setattr(client, "_download_and_verify", _download_and_verify)
    monkeypatch.setattr(client, "_probe_download_url", lambda url: "")


def test_install_from_archive_installs_index_files_and_overrides(tmp_path, monkeypatch):
    client = _client()
    _fake_download(monkeypatch, client)
    install = tmp_path / "server"
    install.mkdir()
    pack = make_mrpack(
        tmp_path,
        make_index(files=[mod_entry("mods/example.jar", env={"server": "required"})]),
        overrides={"overrides/config/example.toml": "greeting = 'hi'"},
    )

    result = client.install_mrpack_archive(pack, install, loader="fabric")

    assert (install / "mods" / "example.jar").is_file()
    assert (install / "config" / "example.toml").read_text() == "greeting = 'hi'"
    assert "mods/example.jar" in result["files_installed"]


def test_install_from_archive_reports_pack_identity_from_the_index(tmp_path, monkeypatch):
    """An uploaded pack has no Modrinth project, so name/version come from the
    manifest and the id fields stay empty rather than being invented."""
    client = _client()
    _fake_download(monkeypatch, client)
    install = tmp_path / "server"
    install.mkdir()
    pack = make_mrpack(tmp_path, make_index(name="My Pack", version_id="4.5.6"))

    result = client.install_mrpack_archive(pack, install, loader="fabric")

    assert result["name"] == "My Pack"
    assert result["version"] == "4.5.6"
    assert result["mc_version"] == "1.20.1"
    assert result["project_id"] is None
    assert result["version_id"] is None


def test_install_from_archive_rejects_a_traversing_index_path(tmp_path, monkeypatch):
    """`path` comes from a file the user supplied, so it is untrusted."""
    client = _client()
    _fake_download(monkeypatch, client)
    install = tmp_path / "server"
    install.mkdir()
    pack = make_mrpack(
        tmp_path, make_index(files=[mod_entry("../../evil.jar", env={"server": "required"})])
    )

    with pytest.raises(ModrinthApiError, match="Invalid path"):
        client.install_mrpack_archive(pack, install, loader="fabric")
    assert not (tmp_path / "evil.jar").exists()


def test_install_from_archive_skips_client_only_entries(tmp_path, monkeypatch):
    client = _client()
    _fake_download(monkeypatch, client)
    install = tmp_path / "server"
    install.mkdir()
    pack = make_mrpack(tmp_path, make_index(files=[
        mod_entry("mods/keep.jar", env={"server": "required"}),
        mod_entry("mods/drop.jar", env={"client": "required", "server": "unsupported"}),
    ]))

    result = client.install_mrpack_archive(pack, install, loader="fabric")

    assert (install / "mods" / "keep.jar").is_file()
    assert not (install / "mods" / "drop.jar").exists()
    assert "mods/drop.jar" in result["files_skipped"]


def test_install_from_archive_leaves_mods_alone_when_a_download_fails(tmp_path, monkeypatch):
    """A clean install wipes mods/, so it must not happen until the pack's
    files are known to be reachable — otherwise a failed install leaves the
    server with no mods at all rather than the ones it had."""
    client = _client()
    monkeypatch.setattr(client, "_probe_download_url", lambda url: "HTTP 404")
    install = tmp_path / "server"
    (install / "mods").mkdir(parents=True)
    (install / "mods" / "existing.jar").write_bytes(b"mine")
    pack = make_mrpack(tmp_path, make_index(files=[
        mod_entry("mods/example.jar", env={"server": "required"}),
    ]))

    with pytest.raises(ModrinthApiError) as excinfo:
        client.install_mrpack_archive(pack, install, loader="fabric", clean_install=True)

    assert excinfo.value.status_code == 409
    assert (install / "mods" / "existing.jar").is_file()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

def _make_server(app, tmp_servers_root, *, version="1.20.1", loader="fabric", path="mrpack-target"):
    from backend.server import storage

    with app.app_context():
        server = storage.create_server({
            "name": path, "version": version, "loader": loader,
            "port": 25599, "installPath": path,
        })
    (tmp_servers_root / "servers" / path).mkdir(parents=True, exist_ok=True)
    return server["id"]


def _upload(client, pack_path, filename="my-pack.mrpack"):
    return client.post(
        f"/api/modrinth/modpack/upload?filename={filename}",
        data=pack_path.read_bytes(),
        content_type="application/octet-stream",
    )


def test_upload_stages_the_pack_and_reports_what_it_declares(client, tmp_path):
    pack = make_mrpack(tmp_path, make_index(name="Cool Pack", loader_key="neoforge"))

    response = _upload(client, pack)

    assert response.status_code == 201
    body = response.get_json()
    assert body["name"] == "Cool Pack"
    assert body["loader"] == "neoforge"
    assert body["minecraft_version"] == "1.20.1"
    assert body["filename"] == "my-pack.mrpack"
    assert mrpack.get(body["upload_id"]) is not None


def test_upload_rejects_a_file_that_is_not_a_modpack(client, tmp_path):
    junk = tmp_path / "notes.txt"
    junk.write_bytes(b"just some text")

    response = _upload(client, junk)

    assert response.status_code == 400
    assert "not a readable .mrpack" in response.get_json()["error"]


def test_upload_rejects_an_empty_body(client):
    response = client.post(
        "/api/modrinth/modpack/upload",
        data=b"",
        content_type="application/octet-stream",
    )
    assert response.status_code == 400
    assert "Empty upload" in response.get_json()["error"]


def test_upload_rejects_a_pack_over_the_size_cap(client, tmp_path, monkeypatch):
    monkeypatch.setenv("FABRICATOR_MAX_MRPACK_UPLOAD_BYTES", "16")
    pack = make_mrpack(tmp_path, make_index())

    response = _upload(client, pack)

    assert response.status_code == 413
    assert "16-byte limit" in response.get_json()["error"]


def test_upload_leaves_nothing_behind_when_the_pack_is_rejected(client, tmp_path):
    junk = tmp_path / "notes.txt"
    junk.write_bytes(b"just some text")

    _upload(client, junk)

    assert list(mrpack.staging_dir().glob("mrpack-*.mrpack")) == []


def test_discard_removes_a_staged_upload(client, tmp_path):
    upload_id = _upload(client, make_mrpack(tmp_path, make_index())).get_json()["upload_id"]

    response = client.delete(f"/api/modrinth/modpack/upload/{upload_id}")

    assert response.status_code == 200
    assert mrpack.get(upload_id) is None
    assert client.delete(f"/api/modrinth/modpack/upload/{upload_id}").status_code == 404


def test_install_puts_the_uploaded_pack_on_the_server(app, client, tmp_servers_root, tmp_path, monkeypatch):
    from backend.modrinth import routes as modrinth_routes

    server_id = _make_server(app, tmp_servers_root)
    _fake_download(monkeypatch, modrinth_routes.modrinth_client)
    pack = make_mrpack(tmp_path, make_index(files=[
        mod_entry("mods/example.jar", env={"server": "required"}),
    ]))
    upload_id = _upload(client, pack).get_json()["upload_id"]

    response = client.post(
        f"/api/modrinth/modpack/upload/{upload_id}/install",
        json={"server_id": server_id, "create_backup": False},
    )

    assert response.status_code == 200
    installed_jar = tmp_servers_root / "servers" / "mrpack-target" / "mods" / "example.jar"
    assert installed_jar.is_file()


def test_install_records_the_pack_on_the_server_as_an_upload(app, client, tmp_servers_root, tmp_path, monkeypatch):
    """The dashboard shows what pack a server runs; an uploaded one has no
    project to link to, so it is recorded by name and marked as a file."""
    from backend.modrinth import routes as modrinth_routes
    from backend.server import storage

    server_id = _make_server(app, tmp_servers_root)
    _fake_download(monkeypatch, modrinth_routes.modrinth_client)
    pack = make_mrpack(tmp_path, make_index(name="Cool Pack", version_id="9.9.9"))
    upload_id = _upload(client, pack).get_json()["upload_id"]

    client.post(
        f"/api/modrinth/modpack/upload/{upload_id}/install",
        json={"server_id": server_id, "create_backup": False},
    )

    with app.app_context():
        recorded = storage.get_server(server_id)["modpack"]
    assert recorded["name"] == "Cool Pack"
    assert recorded["version"] == "9.9.9"
    assert recorded["source"] == "upload"
    assert recorded["fileName"] == "my-pack.mrpack"
    assert recorded["projectId"] is None


def test_install_consumes_the_upload_on_success(app, client, tmp_servers_root, tmp_path, monkeypatch):
    from backend.modrinth import routes as modrinth_routes

    server_id = _make_server(app, tmp_servers_root)
    _fake_download(monkeypatch, modrinth_routes.modrinth_client)
    upload_id = _upload(client, make_mrpack(tmp_path, make_index())).get_json()["upload_id"]

    client.post(
        f"/api/modrinth/modpack/upload/{upload_id}/install",
        json={"server_id": server_id, "create_backup": False},
    )

    assert mrpack.get(upload_id) is None


def test_install_keeps_the_upload_when_files_are_missing(app, client, tmp_servers_root, tmp_path, monkeypatch):
    """The missing-files and uncertain-side flows retry the same pack once the
    user answers; asking them to upload it again for that would be a poor
    trade."""
    from backend.modrinth import routes as modrinth_routes

    server_id = _make_server(app, tmp_servers_root)
    monkeypatch.setattr(
        modrinth_routes.modrinth_client, "_probe_download_url", lambda url: "HTTP 404"
    )
    pack = make_mrpack(tmp_path, make_index(files=[
        mod_entry("mods/example.jar", env={"server": "required"}),
    ]))
    upload_id = _upload(client, pack).get_json()["upload_id"]

    response = client.post(
        f"/api/modrinth/modpack/upload/{upload_id}/install",
        json={"server_id": server_id, "create_backup": False},
    )

    assert response.status_code == 409
    assert response.get_json()["can_continue_with_missing"] is True
    assert mrpack.get(upload_id) is not None


def test_install_refuses_a_pack_built_for_another_minecraft_version(
    app, client, tmp_servers_root, tmp_path, monkeypatch
):
    from backend.modrinth import routes as modrinth_routes

    server_id = _make_server(app, tmp_servers_root, version="1.21.4")
    _fake_download(monkeypatch, modrinth_routes.modrinth_client)
    upload_id = _upload(client, make_mrpack(tmp_path, make_index())).get_json()["upload_id"]

    response = client.post(
        f"/api/modrinth/modpack/upload/{upload_id}/install",
        json={"server_id": server_id, "create_backup": False},
    )

    assert response.status_code == 409
    body = response.get_json()
    assert body["can_continue_with_mismatch"] is True
    assert body["pack_mc_version"] == "1.20.1"
    assert body["server_mc_version"] == "1.21.4"


def test_install_proceeds_with_a_mismatch_once_forced(
    app, client, tmp_servers_root, tmp_path, monkeypatch
):
    """Only the user knows whether a pack happens to be portable, so the
    mismatch is a confirmation rather than a hard stop."""
    from backend.modrinth import routes as modrinth_routes

    server_id = _make_server(app, tmp_servers_root, version="1.21.4")
    _fake_download(monkeypatch, modrinth_routes.modrinth_client)
    upload_id = _upload(client, make_mrpack(tmp_path, make_index())).get_json()["upload_id"]

    response = client.post(
        f"/api/modrinth/modpack/upload/{upload_id}/install",
        json={"server_id": server_id, "create_backup": False, "force": True},
    )

    assert response.status_code == 200


def test_install_rejects_an_upload_that_is_gone(app, client, tmp_servers_root):
    server_id = _make_server(app, tmp_servers_root)

    response = client.post(
        "/api/modrinth/modpack/upload/deadbeef/install",
        json={"server_id": server_id, "create_backup": False},
    )

    assert response.status_code == 404
    assert "upload the .mrpack again" in response.get_json()["error"]


def test_install_requires_a_stopped_server(app, client, tmp_servers_root, tmp_path, monkeypatch):
    from backend.modrinth import routes as modrinth_routes

    server_id = _make_server(app, tmp_servers_root)
    upload_id = _upload(client, make_mrpack(tmp_path, make_index())).get_json()["upload_id"]
    monkeypatch.setattr(
        modrinth_routes._registry(), "get_status", lambda sid: {"status": "running"}
    )

    response = client.post(
        f"/api/modrinth/modpack/upload/{upload_id}/install",
        json={"server_id": server_id, "create_backup": False},
    )

    assert response.status_code == 400
    assert "Stop the server" in response.get_json()["error"]
