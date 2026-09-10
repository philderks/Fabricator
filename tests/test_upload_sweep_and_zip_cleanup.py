"""Housekeeping for the two files a failed request can strand on disk.

* A `?format=zip` snapshot download builds a temp zip. The after-request
  cleanup is only registered once the conversion returns, so a conversion that
  raised (corrupt archive, disk full) left the partial zip in the system temp
  dir permanently.
* World uploads are streamed to `.uploads/` before the import worker starts.
  The worker unlinks its own file, but nothing covered a panel killed between
  the 202 and the worker finishing — orphaning a file up to the 10 GiB cap
  with nothing left to remember it.
"""
from __future__ import annotations

import os
import tarfile
import tempfile
import time
from pathlib import Path

import pytest


# --------------------------------------------------------------------------- #
# #5 — temp zip cleanup
# --------------------------------------------------------------------------- #

def _temp_zips() -> set:
    root = Path(tempfile.gettempdir())
    try:
        return {p for p in root.glob("*.zip")}
    except OSError:  # pragma: no cover
        return set()


def test_failed_zip_conversion_leaves_no_temp_file(app, tmp_path):
    # The `app` fixture is what establishes the import order: importing
    # backend.backups.routes first hits a pre-existing cycle
    # (backups.storage -> backend.core.config -> backend.core -> app ->
    # backups.routes). Unrelated to this fix, but it decides how to import here.
    from backend.backups import routes

    corrupt = tmp_path / "corrupt.tar"
    corrupt.write_bytes(b"this is definitely not a tar archive")

    before = _temp_zips()
    with pytest.raises(Exception):
        routes._convert_to_zip(corrupt)
    leaked = _temp_zips() - before

    assert not leaked, f"conversion leaked temp zip(s): {leaked}"


def test_successful_zip_conversion_returns_a_real_file(app, tmp_path):
    """The happy path still hands back a zip the caller can send — the cleanup
    must not have become over-eager."""
    from backend.backups import routes

    source = tmp_path / "snap.tar"
    payload = tmp_path / "server.properties"
    payload.write_text("port=25565\n", encoding="utf-8")
    with tarfile.open(source, "w") as tf:
        tf.add(payload, arcname="server.properties")

    zip_path, name = routes._convert_to_zip(source)
    try:
        assert zip_path.exists()
        assert zip_path.stat().st_size > 0
        assert name == "snap.zip"
    finally:
        zip_path.unlink(missing_ok=True)


# --------------------------------------------------------------------------- #
# #8 — abandoned world uploads
# --------------------------------------------------------------------------- #

@pytest.fixture
def uploads(tmp_servers_root, monkeypatch):
    """A world-import staging dir wired to the tmp servers root."""
    from backend.backups import world_import

    directory = world_import.uploads_dir()
    directory.mkdir(parents=True, exist_ok=True)
    world_import._active_uploads.clear()
    yield world_import, directory
    world_import._active_uploads.clear()


def _stale(directory: Path, name: str, age_seconds: float) -> Path:
    path = directory / name
    path.write_bytes(b"x" * 16)
    old = time.time() - age_seconds
    os.utime(path, (old, old))
    return path


def test_abandoned_upload_past_the_ttl_is_swept(uploads):
    world_import, directory = uploads
    orphan = _stale(
        directory, "world-srv_x-abc.upload", world_import.UPLOAD_TTL_SECONDS + 60
    )

    assert world_import.sweep_stale_uploads() == 1
    assert not orphan.exists()


def test_a_recent_upload_is_left_alone(uploads):
    """An upload from minutes ago may belong to an import that is still
    starting up — the TTL is what keeps the sweep off it."""
    world_import, directory = uploads
    fresh = _stale(directory, "world-srv_x-def.upload", 60)

    assert world_import.sweep_stale_uploads() == 0
    assert fresh.exists()


def test_an_in_flight_upload_is_never_swept(uploads):
    """However old it is: a long import must not have its archive pulled out
    from under it."""
    world_import, directory = uploads
    live = _stale(
        directory, "world-srv_x-ghi.upload", world_import.UPLOAD_TTL_SECONDS * 10
    )
    world_import._active_uploads.add(live)

    assert world_import.sweep_stale_uploads() == 0
    assert live.exists()


def test_sweep_ignores_other_files_in_the_shared_staging_dir(uploads):
    """`.uploads` is shared with staged .mrpack archives, which have their own
    sweep and TTL bookkeeping. This one must only claim its own files."""
    world_import, directory = uploads
    mrpack = _stale(
        directory, "mrpack-deadbeef.mrpack", world_import.UPLOAD_TTL_SECONDS + 60
    )
    unrelated = _stale(
        directory, "notes.txt", world_import.UPLOAD_TTL_SECONDS + 60
    )

    assert world_import.sweep_stale_uploads() == 0
    assert mrpack.exists()
    assert unrelated.exists()


def test_sweep_survives_a_missing_staging_dir(tmp_servers_root):
    """Nothing has uploaded yet — the sweep runs on every upload and at boot,
    so an absent directory must be a quiet no-op, not an error."""
    from backend.backups import world_import

    directory = world_import.uploads_dir()
    if directory.exists():
        for child in directory.iterdir():
            child.unlink()
        directory.rmdir()

    assert world_import.sweep_stale_uploads() == 0


def test_upload_paths_are_unique_and_in_the_staging_dir(tmp_servers_root):
    from backend.backups import world_import

    first = world_import.new_upload_path("srv_a")
    second = world_import.new_upload_path("srv_a")

    assert first != second
    assert first.parent == world_import.uploads_dir()
    assert first.name.startswith("world-srv_a-")
    assert first.suffix == ".upload"


def test_uploads_dir_matches_the_mrpack_staging_dir(tmp_servers_root):
    """Both upload kinds are documented as sharing one folder an operator can
    inspect or clear. If they ever diverge, each sweep would be blind to the
    other's directory."""
    from backend.backups import world_import
    from backend.modrinth import mrpack

    assert world_import.uploads_dir() == mrpack.staging_dir()


def test_world_import_route_sweeps_before_streaming(
    client, app, tmp_servers_root, monkeypatch
):
    """The on-upload sweep is what reclaims space before the next (potentially
    multi-gigabyte) upload lands."""
    from backend.backups import world_import
    from backend.server import storage

    with app.app_context():
        server = storage.create_server({
            "name": "wi", "version": "1.21.4", "loader": "paper",
            "port": 25941, "installPath": "wi",
        })
    (tmp_servers_root / "servers" / "wi").mkdir(parents=True, exist_ok=True)

    directory = world_import.uploads_dir()
    directory.mkdir(parents=True, exist_ok=True)
    orphan = _stale(
        directory, "world-old-xyz.upload", world_import.UPLOAD_TTL_SECONDS + 60
    )

    # Body is not a valid archive, so the request 400s — the sweep still ran.
    resp = client.post(
        f"/api/servers/{server['id']}/world-import", data=b"not an archive"
    )
    assert resp.status_code == 400
    assert not orphan.exists(), "route did not sweep before streaming"
