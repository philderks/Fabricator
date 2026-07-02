"""Restore orchestrator (``backend.backups.restore``).

Highest-priority pin: a failure in the mandatory safety-snapshot step
MUST abort the restore and leave the live server dir untouched. The
brief was explicit and this is the non-negotiable safety guarantee for
the whole feature.

Also exercises:

- ``safe_extract_tar`` rejects traversal attempts.
- in_place overlay preserves live-only files while applying archive
  contents on top.
- reset mode atomic-swaps the live dir for the staged tree.
"""
from __future__ import annotations

import json
import tarfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def restore_env(tmp_servers_root, monkeypatch):
    """Reload storage + restore against a tmp BACKUPS_DIR."""
    monkeypatch.setenv("BACKUPS_DIR", str(tmp_servers_root / "backups-r"))
    monkeypatch.setenv("FABRICATOR_DISABLE_SCHEDULER", "1")

    import importlib
    import backend.backups.storage as storage
    import backend.backups.restore as restore
    importlib.reload(storage)
    importlib.reload(restore)
    storage.reset_for_tests()

    yield {
        "storage": storage,
        "restore": restore,
        "tmp": Path(tmp_servers_root),
    }
    storage.reset_for_tests()


def _seed_server(tmp_root: Path, server_id: str):
    """Seed servers.json + a populated install dir."""
    index = tmp_root / "servers.json"
    index.write_text(
        json.dumps(
            [
                {
                    "id": server_id,
                    "name": "R",
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
    (install / "server.properties").write_text("live-config\n", encoding="utf-8")
    world = install / "world"
    world.mkdir(exist_ok=True)
    (world / "level.dat").write_text("LIVE-WORLD", encoding="utf-8")
    return install


def _write_plain_tar(path: Path, files: dict):
    with tarfile.open(path, "w") as tf:
        for name, content in files.items():
            info = tarfile.TarInfo(name)
            payload = content.encode("utf-8")
            info.size = len(payload)
            import io
            tf.addfile(info, io.BytesIO(payload))


def _fake_registry(install_path: Path):
    registry = MagicMock()
    registry.resolve_install_path.return_value = install_path
    registry.get_status.return_value = {"status": "stopped"}
    registry.stop_server.return_value = {"status": "stopped"}
    registry.start_server.return_value = {"status": "running"}
    registry._instances = {}
    return registry


def test_safety_snapshot_failure_aborts_restore_and_preserves_live(
    restore_env, monkeypatch, tmp_path
):
    """When the safety .tar build raises, the live dir must NOT be touched."""
    storage = restore_env["storage"]
    restore = restore_env["restore"]
    tmp = restore_env["tmp"]

    install = _seed_server(tmp, "srv_r1")
    storage_dir = tmp_path / "store"
    storage_dir.mkdir()

    cfg = storage.create_config(
        "srv_r1",
        {"name": "Safe", "storagePath": str(storage_dir), "compress": False},
    )
    archive = storage_dir / "snap.tar"
    _write_plain_tar(archive, {
        "server.properties": "RESTORED-CONFIG\n",
        "world/level.dat": "RESTORED-WORLD",
    })
    snap = storage.record_snapshot(
        "srv_r1",
        {
            "configId": cfg["id"],
            "type": "backup",
            "filePath": str(archive),
            "fileName": archive.name,
            "sizeBytes": archive.stat().st_size,
            "status": "success",
        },
    )

    registry = _fake_registry(install)
    monkeypatch.setattr(
        restore, "get_server_process_registry", lambda: registry
    )

    # Force the safety-snapshot build to raise.
    def boom(*_a, **_kw):
        raise OSError("simulated safety-tar failure")

    monkeypatch.setattr(restore, "_write_safety_snapshot", boom)

    with pytest.raises(OSError):
        restore.run_restore(snap["id"], mode="reset")

    # Live tree intact — no overlay, no swap, original contents preserved.
    assert (install / "server.properties").read_text() == "live-config\n"
    assert (install / "world" / "level.dat").read_text() == "LIVE-WORLD"
    # An error snapshot entry was recorded for the audit trail.
    snapshots = storage.list_snapshots("srv_r1")
    assert any(
        s["type"] == "restore" and s["status"] == "error" for s in snapshots
    )


def test_restore_of_running_server_reaches_done_phase(
    restore_env, monkeypatch, tmp_path
):
    """A restore of a server that was RUNNING must end in the terminal 'done'
    phase, not stay stuck in 'restarting' (which keeps is_active() True and
    hangs the frontend poll loop forever)."""
    from backend.backups import progress

    storage = restore_env["storage"]
    restore = restore_env["restore"]
    tmp = restore_env["tmp"]

    install = _seed_server(tmp, "srv_running")
    storage_dir = tmp_path / "store"
    storage_dir.mkdir()
    cfg = storage.create_config(
        "srv_running",
        {"name": "Run", "storagePath": str(storage_dir), "compress": False},
    )
    archive = storage_dir / "snap.tar"
    _write_plain_tar(archive, {"world/level.dat": "RESTORED"})
    snap = storage.record_snapshot(
        "srv_running",
        {
            "configId": cfg["id"],
            "type": "backup",
            "filePath": str(archive),
            "fileName": archive.name,
            "sizeBytes": archive.stat().st_size,
            "status": "success",
        },
    )

    registry = _fake_registry(install)
    registry.get_status.return_value = {"status": "running"}
    monkeypatch.setattr(restore, "get_server_process_registry", lambda: registry)

    job_id = progress.generate_job_id("bjr")
    restore.run_restore(snap["id"], mode="in_place", job_id=job_id)

    registry.start_server.assert_called_once()          # it WAS restarted
    entry = progress.get(job_id)
    assert entry.get("phase") == "done", f"restore stuck in {entry.get('phase')!r}"
    assert not progress.is_active(job_id)


def test_safety_snapshot_excludes_nested_storage_subtree(restore_env, tmp_path):
    """A storagePath nested inside the install tree must be excluded from the
    safety tar (no recursive self-inclusion of prior backups), while unrelated
    siblings under the same intermediate dir are still captured."""
    restore = restore_env["restore"]
    install = tmp_path / "install"
    (install / "world").mkdir(parents=True)
    (install / "world" / "level.dat").write_text("W")
    nested = install / "data" / "backups"          # storagePath two levels deep
    nested.mkdir(parents=True)
    (nested / "old-backup.tar").write_bytes(b"HUGE" * 4096)
    (install / "data" / "keepme.dat").write_text("KEEP")

    cfg = {"id": "c1", "name": "Nested"}
    rec = restore._write_safety_snapshot(
        install_path=install, cfg=cfg, storage_path=nested, server_id="srv_nested_x"
    )

    with tarfile.open(rec["filePath"]) as tf:
        names = set(tf.getnames())
    assert "world/level.dat" in names
    assert "data/keepme.dat" in names                              # sibling kept
    assert not any(n.startswith("data/backups") for n in names), names  # storage subtree gone


def test_in_place_restore_overlays_and_preserves_extra_files(
    restore_env, monkeypatch, tmp_path
):
    storage = restore_env["storage"]
    restore = restore_env["restore"]
    tmp = restore_env["tmp"]

    install = _seed_server(tmp, "srv_r2")
    # Add an extra file that only exists in live — overlay must preserve it.
    (install / "ops.json").write_text("[]", encoding="utf-8")
    storage_dir = tmp_path / "store2"
    storage_dir.mkdir()

    cfg = storage.create_config(
        "srv_r2",
        {"name": "OL", "storagePath": str(storage_dir), "compress": False},
    )
    archive = storage_dir / "snap.tar"
    _write_plain_tar(archive, {
        "server.properties": "RESTORED-CONFIG\n",
        "world/level.dat": "RESTORED-WORLD",
    })
    snap = storage.record_snapshot(
        "srv_r2",
        {
            "configId": cfg["id"],
            "type": "backup",
            "filePath": str(archive),
            "fileName": archive.name,
            "sizeBytes": archive.stat().st_size,
            "status": "success",
        },
    )

    registry = _fake_registry(install)
    monkeypatch.setattr(
        restore, "get_server_process_registry", lambda: registry
    )

    restore.run_restore(snap["id"], mode="in_place")

    assert (install / "server.properties").read_text() == "RESTORED-CONFIG\n"
    assert (install / "world" / "level.dat").read_text() == "RESTORED-WORLD"
    # The extra live-only file survived the overlay.
    assert (install / "ops.json").exists()


def test_reset_restore_swaps_in_staged_tree(
    restore_env, monkeypatch, tmp_path
):
    storage = restore_env["storage"]
    restore = restore_env["restore"]
    tmp = restore_env["tmp"]

    install = _seed_server(tmp, "srv_r3")
    (install / "ops.json").write_text("[]", encoding="utf-8")
    storage_dir = tmp_path / "store3"
    storage_dir.mkdir()

    cfg = storage.create_config(
        "srv_r3",
        {"name": "RS", "storagePath": str(storage_dir), "compress": False},
    )
    archive = storage_dir / "snap.tar"
    _write_plain_tar(archive, {
        "server.properties": "RESTORED-CONFIG\n",
        "world/level.dat": "RESTORED-WORLD",
    })
    snap = storage.record_snapshot(
        "srv_r3",
        {
            "configId": cfg["id"],
            "type": "backup",
            "filePath": str(archive),
            "fileName": archive.name,
            "sizeBytes": archive.stat().st_size,
            "status": "success",
        },
    )

    registry = _fake_registry(install)
    monkeypatch.setattr(
        restore, "get_server_process_registry", lambda: registry
    )

    restore.run_restore(snap["id"], mode="reset")

    assert (install / "server.properties").read_text() == "RESTORED-CONFIG\n"
    # Reset mode replaces the dir wholesale — ops.json is gone.
    assert not (install / "ops.json").exists()


def test_safe_extract_tar_rejects_traversal(tmp_path):
    """Path-traversal attempts via tar members must be rejected."""
    from backend.utils.zip import safe_extract_tar

    destination = tmp_path / "dst"
    destination.mkdir()

    archive = tmp_path / "evil.tar"
    with tarfile.open(archive, "w") as tf:
        info = tarfile.TarInfo("../escape.txt")
        info.size = 4
        import io
        tf.addfile(info, io.BytesIO(b"pwn!"))

    with tarfile.open(archive, "r") as tf:
        with pytest.raises(ValueError):
            safe_extract_tar(tf, destination)

    assert not (tmp_path / "escape.txt").exists()


def test_safe_extract_tar_rejects_symlink_members(tmp_path):
    """Symlink members must be rejected up-front."""
    from backend.utils.zip import safe_extract_tar

    destination = tmp_path / "dst"
    destination.mkdir()

    archive = tmp_path / "evil-link.tar"
    with tarfile.open(archive, "w") as tf:
        info = tarfile.TarInfo("link")
        info.type = tarfile.SYMTYPE
        info.linkname = "/etc/passwd"
        tf.addfile(info)

    with tarfile.open(archive, "r") as tf:
        with pytest.raises(ValueError):
            safe_extract_tar(tf, destination)
