"""World import orchestrator (``backend.backups.world_import``).

Highest-priority pin (mirrors ``test_backups_restore``): a failure in the
mandatory safety-snapshot step MUST abort the import and leave the live
world dirs untouched.

Also exercises:

- Layout detection: server-format worlds vs singleplayer saves.
- Singleplayer → server conversion (DIM-1/DIM1 split into
  ``_nether``/``_the_end`` sibling dirs).
- A successful end-to-end import replaces only the world dirs.
- Upload streaming cap + archive validation.
"""
from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def import_env(tmp_servers_root, monkeypatch):
    """Reload storage + world_import against a tmp BACKUPS_DIR."""
    monkeypatch.setenv("BACKUPS_DIR", str(tmp_servers_root / "backups-w"))
    monkeypatch.setenv("FABRICATOR_DISABLE_SCHEDULER", "1")

    import importlib
    import backend.backups.storage as storage
    import backend.backups.world_import as world_import
    importlib.reload(storage)
    importlib.reload(world_import)
    storage.reset_for_tests()

    yield {
        "storage": storage,
        "world_import": world_import,
        "tmp": Path(tmp_servers_root),
    }
    storage.reset_for_tests()


def _seed_server(tmp_root: Path, server_id: str):
    """Seed servers.json + a populated install dir with a live world."""
    index = tmp_root / "servers.json"
    index.write_text(
        json.dumps(
            [
                {
                    "id": server_id,
                    "name": "W",
                    "version": "1.20.1",
                    "loader": "fabric",
                    "port": 25565,
                    "installPath": server_id,
                    "levelName": "world",
                    "status": "stopped",
                }
            ]
        ),
        encoding="utf-8",
    )
    install = tmp_root / "servers" / server_id
    install.mkdir(parents=True, exist_ok=True)
    (install / "server.properties").write_text(
        "level-name=world\n", encoding="utf-8"
    )
    world = install / "world"
    world.mkdir(exist_ok=True)
    (world / "level.dat").write_text("LIVE-WORLD", encoding="utf-8")
    return install


def _fake_registry(install_path: Path):
    registry = MagicMock()
    registry.resolve_install_path.return_value = install_path
    registry.get_status.return_value = {"status": "stopped"}
    registry.stop_server.return_value = {"status": "stopped"}
    registry.start_server.return_value = {"status": "running"}
    registry._instances = {}
    return registry


def _zip(path: Path, files: dict):
    """Write a zip whose members are the given posix-path -> content map.

    Directory-only entries (keys ending in ``/``) are written as explicit
    dir members so empty dimension dirs survive.
    """
    with zipfile.ZipFile(path, "w") as zf:
        for name, content in files.items():
            if name.endswith("/"):
                zf.writestr(name, "")
            else:
                zf.writestr(name, content)


# ---------------------------------------------------------------------------
# Layout detection + normalization (pure)
# ---------------------------------------------------------------------------


def test_detect_server_layout(import_env, tmp_path):
    world_import = import_env["world_import"]
    root = tmp_path / "ex"
    (root / "world").mkdir(parents=True)
    (root / "world" / "level.dat").write_text("x")
    (root / "world_nether" / "DIM-1").mkdir(parents=True)
    (root / "world_the_end" / "DIM1").mkdir(parents=True)

    detection = world_import.detect_world_layout(root)
    assert detection["layout"] == "server"
    assert detection["world_root"].name == "world"


def test_detect_singleplayer_layout(import_env, tmp_path):
    world_import = import_env["world_import"]
    root = tmp_path / "ex"
    save = root / "MyWorld"
    (save / "region").mkdir(parents=True)
    (save / "level.dat").write_text("x")
    (save / "DIM-1" / "region").mkdir(parents=True)
    (save / "DIM1" / "region").mkdir(parents=True)

    detection = world_import.detect_world_layout(root)
    assert detection["layout"] == "singleplayer"
    assert detection["world_root"].name == "MyWorld"


def test_normalize_singleplayer_splits_dimensions(import_env, tmp_path):
    world_import = import_env["world_import"]
    save = tmp_path / "MyWorld"
    (save / "region").mkdir(parents=True)
    (save / "level.dat").write_text("LEVEL")
    (save / "DIM-1" / "region").mkdir(parents=True)
    (save / "DIM-1" / "region" / "r.0.0.mca").write_text("NETHER")
    (save / "DIM1" / "region").mkdir(parents=True)
    (save / "DIM1" / "region" / "r.0.0.mca").write_text("END")

    dest = tmp_path / "out"
    produced = world_import.normalize_world(
        world_root=save, layout="singleplayer", level_name="world", destination=dest
    )

    assert set(produced) == {"world", "world_nether", "world_the_end"}
    # Overworld keeps level.dat but NOT the DIM dirs.
    assert (dest / "world" / "level.dat").read_text() == "LEVEL"
    assert not (dest / "world" / "DIM-1").exists()
    # Nether/End were lifted into the server-split sibling dirs.
    assert (dest / "world_nether" / "DIM-1" / "region" / "r.0.0.mca").read_text() == "NETHER"
    assert (dest / "world_the_end" / "DIM1" / "region" / "r.0.0.mca").read_text() == "END"


def test_normalize_server_renames_to_level_name(import_env, tmp_path):
    world_import = import_env["world_import"]
    root = tmp_path / "ex"
    (root / "world").mkdir(parents=True)
    (root / "world" / "level.dat").write_text("OW")
    (root / "world_nether").mkdir()
    (root / "world_nether" / "marker").write_text("N")

    dest = tmp_path / "out"
    produced = world_import.normalize_world(
        world_root=root / "world",
        layout="server",
        level_name="earth",
        destination=dest,
    )
    assert set(produced) == {"earth", "earth_nether"}
    assert (dest / "earth" / "level.dat").read_text() == "OW"
    assert (dest / "earth_nether" / "marker").read_text() == "N"


# ---------------------------------------------------------------------------
# End-to-end orchestration
# ---------------------------------------------------------------------------


def test_safety_failure_aborts_import_and_preserves_live(
    import_env, monkeypatch, tmp_path
):
    world_import = import_env["world_import"]
    tmp = import_env["tmp"]
    install = _seed_server(tmp, "srv_w1")

    archive = tmp_path / "up.zip"
    _zip(archive, {"world/level.dat": "NEW-WORLD"})

    registry = _fake_registry(install)
    monkeypatch.setattr(
        world_import, "get_server_process_registry", lambda: registry
    )

    def boom(*_a, **_kw):
        raise OSError("simulated safety-tar failure")

    monkeypatch.setattr(world_import, "_write_safety_snapshot", boom)

    with pytest.raises(OSError):
        world_import.run_world_import(
            "srv_w1", archive, original_name="up.zip"
        )

    # Live world untouched; upload consumed.
    assert (install / "world" / "level.dat").read_text() == "LIVE-WORLD"
    assert not archive.exists()
    storage = import_env["storage"]
    assert any(
        s["type"] == "import" and s["status"] == "error"
        for s in storage.list_snapshots("srv_w1")
    )


def test_successful_import_replaces_world(import_env, monkeypatch, tmp_path):
    world_import = import_env["world_import"]
    storage = import_env["storage"]
    tmp = import_env["tmp"]
    install = _seed_server(tmp, "srv_w2")
    # A non-world file must survive an import (only world dirs are touched).
    (install / "ops.json").write_text("[]", encoding="utf-8")

    archive = tmp_path / "up.zip"
    _zip(
        archive,
        {
            "world/level.dat": "IMPORTED",
            "world/region/r.0.0.mca": "CHUNK",
        },
    )

    registry = _fake_registry(install)
    monkeypatch.setattr(
        world_import, "get_server_process_registry", lambda: registry
    )

    record = world_import.run_world_import(
        "srv_w2", archive, original_name="up.zip"
    )

    assert (install / "world" / "level.dat").read_text() == "IMPORTED"
    assert (install / "world" / "region" / "r.0.0.mca").read_text() == "CHUNK"
    assert (install / "ops.json").read_text() == "[]"
    assert record["type"] == "import" and record["status"] == "success"
    # A safety snapshot was recorded before the swap.
    assert any(
        s["type"] == "safety" for s in storage.list_snapshots("srv_w2")
    )
    assert not archive.exists()


def test_running_server_is_stopped_then_restarted(
    import_env, monkeypatch, tmp_path
):
    world_import = import_env["world_import"]
    tmp = import_env["tmp"]
    install = _seed_server(tmp, "srv_w3")

    archive = tmp_path / "up.zip"
    _zip(archive, {"world/level.dat": "IMPORTED"})

    registry = _fake_registry(install)
    registry.get_status.return_value = {"status": "running"}
    monkeypatch.setattr(
        world_import, "get_server_process_registry", lambda: registry
    )

    world_import.run_world_import("srv_w3", archive, original_name="up.zip")

    registry.stop_server.assert_called_once()
    registry.start_server.assert_called_once()


# ---------------------------------------------------------------------------
# Upload streaming + validation
# ---------------------------------------------------------------------------


def test_stream_upload_cap_rejects_oversize(import_env, tmp_path):
    world_import = import_env["world_import"]
    dest = tmp_path / "u.bin"
    stream = io.BytesIO(b"x" * 5000)
    with pytest.raises(world_import.UploadTooLargeError):
        world_import.stream_upload_to_temp(stream, dest, max_bytes=1000)
    # Partial file cleaned up.
    assert not dest.exists()


def test_validate_rejects_non_world_archive(import_env, tmp_path):
    world_import = import_env["world_import"]
    archive = tmp_path / "notworld.zip"
    _zip(archive, {"readme.txt": "hello"})
    with pytest.raises(world_import.InvalidWorldArchiveError):
        world_import.validate_upload_archive(archive)


def test_validate_accepts_world_archive(import_env, tmp_path):
    world_import = import_env["world_import"]
    archive = tmp_path / "world.zip"
    _zip(archive, {"world/level.dat": "x"})
    assert world_import.validate_upload_archive(archive) == "zip"


def test_validate_accepts_world_archive_with_root_level_dat(import_env, tmp_path):
    """A zip of the world folder's CONTENTS — level.dat at the archive root — is
    a valid world. _find_level_dat_root returns "" (not None) for that layout,
    so a truthiness check would wrongly reject this common packaging."""
    world_import = import_env["world_import"]
    archive = tmp_path / "rootworld.zip"
    _zip(archive, {"level.dat": "x", "region/r.0.0.mca": "y"})
    assert world_import.validate_upload_archive(archive) == "zip"


# ---------------------------------------------------------------------------
# HTTP route (POST /api/servers/<id>/world-import)
# ---------------------------------------------------------------------------


@pytest.fixture
def env(tmp_servers_root, monkeypatch):
    """Lightweight env for route tests (storage resolves dirs lazily)."""
    monkeypatch.setenv("BACKUPS_DIR", str(tmp_servers_root / "backups-route-w"))
    monkeypatch.setenv("FABRICATOR_DISABLE_SCHEDULER", "1")
    import backend.backups.storage as bs
    bs.reset_for_tests()
    yield {"storage": bs, "tmp": Path(tmp_servers_root)}
    bs.reset_for_tests()


def test_route_accepts_world_upload_and_returns_job(client, env, monkeypatch):
    _seed_server(env["tmp"], "srv_route_w")

    import backend.backups.routes as routes

    captured = {}

    def fake_async(server_id, temp_path, *, original_name):
        # The route should have streamed a valid world archive to disk.
        captured["server_id"] = server_id
        captured["exists"] = Path(temp_path).exists()
        captured["name"] = original_name
        Path(temp_path).unlink(missing_ok=True)
        return "bjw_test"

    monkeypatch.setattr(
        routes.world_import, "run_world_import_async", fake_async
    )

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("world/level.dat", "x")
    resp = client.post(
        "/api/servers/srv_route_w/world-import?filename=MySave.zip",
        data=buf.getvalue(),
        content_type="application/octet-stream",
    )
    assert resp.status_code == 202, resp.get_json()
    assert resp.get_json()["job_id"] == "bjw_test"
    assert captured["server_id"] == "srv_route_w"
    assert captured["exists"] is True
    assert captured["name"] == "MySave.zip"


def test_route_rejects_empty_upload(client, env):
    _seed_server(env["tmp"], "srv_route_empty")
    resp = client.post(
        "/api/servers/srv_route_empty/world-import",
        data=b"",
        content_type="application/octet-stream",
    )
    assert resp.status_code == 400


def test_route_rejects_non_world_archive(client, env):
    _seed_server(env["tmp"], "srv_route_bad")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("readme.txt", "nope")
    resp = client.post(
        "/api/servers/srv_route_bad/world-import",
        data=buf.getvalue(),
        content_type="application/octet-stream",
    )
    assert resp.status_code == 400
    assert "level.dat" in resp.get_json()["error"]


def test_route_unknown_server_404(client, env):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("world/level.dat", "x")
    resp = client.post(
        "/api/servers/does-not-exist/world-import",
        data=buf.getvalue(),
        content_type="application/octet-stream",
    )
    assert resp.status_code == 404
