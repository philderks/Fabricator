"""Backup orchestrator (``backend.backups.service``).

Pins:
- Manual + scheduled runs both apply retention (the brief was explicit).
- Flush waits for ``Saved the game`` and times out cleanly (records a
  warning on the snapshot, does not abort the backup).
- Staging copy honours user exclusions AND always excludes ``backups/**``.
- Hybrid compress (compress=True) produces an outer tar containing
  ``data.tar.gz`` + ``worlds.tar``.
- Failure path records an error-status snapshot AND re-raises so the
  worker thread's progress entry flips to failed.
"""
from __future__ import annotations

import json
import os
import tarfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def backups_env(tmp_servers_root, monkeypatch):
    """Reload storage + service against a tmp BACKUPS_DIR."""
    monkeypatch.setenv("BACKUPS_DIR", str(tmp_servers_root / "backups-state"))
    monkeypatch.setenv("FABRICATOR_DISABLE_SCHEDULER", "1")
    import importlib
    import backend.backups.storage as storage
    import backend.backups.service as service
    importlib.reload(storage)
    importlib.reload(service)
    storage.reset_for_tests()
    yield {
        "storage": storage,
        "service": service,
        "tmp": Path(tmp_servers_root),
    }
    storage.reset_for_tests()


def _seed_server(tmp_root: Path, server_id: str = "srv_b"):
    """Write servers.json + a populated install dir for ``server_id``."""
    index = tmp_root / "servers.json"
    payload = [
        {
            "id": server_id,
            "name": "Backup target",
            "version": "1.20.1",
            "loader": "fabric",
            "port": 25565,
            "installPath": server_id,
            "levelName": "world",
            "status": "stopped",
        }
    ]
    index.write_text(json.dumps(payload), encoding="utf-8")
    install = tmp_root / "servers" / server_id
    install.mkdir(parents=True, exist_ok=True)
    (install / "server.properties").write_text("port=25565\n", encoding="utf-8")
    world = install / "world"
    world.mkdir(exist_ok=True)
    (world / "level.dat").write_text("LIVE-WORLD", encoding="utf-8")
    nether = install / "world_nether"
    nether.mkdir(exist_ok=True)
    (nether / "region.dat").write_text("NETHER", encoding="utf-8")
    logs = install / "logs"
    logs.mkdir(exist_ok=True)
    (logs / "latest.log").write_text("log line", encoding="utf-8")
    return install


def _fake_registry(install_path: Path, *, running: bool = False):
    """Return a MagicMock registry whose API matches what service.py uses."""
    registry = MagicMock()
    registry.resolve_install_path.return_value = install_path
    registry.get_status.return_value = {
        "status": "running" if running else "stopped"
    }
    registry.send_command.return_value = {"success": True}
    manager = MagicMock()
    manager.wait_for_log.return_value = True
    registry.get_manager.return_value = None  # no live manager by default
    return registry, manager


def test_backup_creates_archive_and_records_snapshot(
    backups_env, monkeypatch, tmp_path
):
    storage = backups_env["storage"]
    service = backups_env["service"]
    tmp = backups_env["tmp"]

    install = _seed_server(tmp, "srv_b1")
    storage_dir = tmp_path / "store"

    cfg = storage.create_config(
        "srv_b1",
        {
            "name": "Daily",
            "storagePath": str(storage_dir),
            "maxSnapshots": 0,
            "flush": False,
            "shutdown": False,
            "compress": True,
            "exclusions": ["logs/**"],
        },
    )

    registry, _ = _fake_registry(install, running=False)
    monkeypatch.setattr(
        service, "get_server_process_registry", lambda: registry
    )

    snapshot = service.run_backup(cfg["id"], trigger="manual")

    assert snapshot["status"] == "success"
    archive_path = Path(snapshot["filePath"])
    assert archive_path.exists()
    assert archive_path.parent == storage_dir
    # Hybrid archive layout.
    with tarfile.open(archive_path, "r") as tf:
        names = set(tf.getnames())
    assert {"data.tar.gz", "worlds.tar"}.issubset(names)


def test_flush_warning_does_not_abort_backup(
    backups_env, monkeypatch, tmp_path
):
    """Timing out on the 'Saved the game' log records a warning, not an error."""
    storage = backups_env["storage"]
    service = backups_env["service"]
    tmp = backups_env["tmp"]

    install = _seed_server(tmp, "srv_b2")
    storage_dir = tmp_path / "store2"

    cfg = storage.create_config(
        "srv_b2",
        {
            "name": "Daily",
            "storagePath": str(storage_dir),
            "maxSnapshots": 0,
            "flush": True,
            "shutdown": False,
            "compress": False,
        },
    )

    registry, manager = _fake_registry(install, running=True)
    manager.wait_for_log.return_value = False  # simulate timeout
    registry.get_manager.return_value = manager
    monkeypatch.setattr(
        service, "get_server_process_registry", lambda: registry
    )

    snapshot = service.run_backup(cfg["id"], trigger="manual")

    assert snapshot["status"] == "warning"
    assert "Timed out" in (snapshot["message"] or "")
    # Archive still produced even with the flush warning.
    assert Path(snapshot["filePath"]).exists()


def test_retention_runs_on_manual_trigger(
    backups_env, monkeypatch, tmp_path
):
    """``maxSnapshots`` retention deletes older archives + records.

    The brief was explicit: retention runs on manual and scheduled runs.
    """
    storage = backups_env["storage"]
    service = backups_env["service"]
    tmp = backups_env["tmp"]

    install = _seed_server(tmp, "srv_b3")
    storage_dir = tmp_path / "store3"
    storage_dir.mkdir()

    cfg = storage.create_config(
        "srv_b3",
        {
            "name": "Retained",
            "storagePath": str(storage_dir),
            "maxSnapshots": 2,
            "flush": False,
            "shutdown": False,
            "compress": False,
        },
    )

    # Seed three pre-existing backup snapshot records pointing at three
    # archive files on disk (so the retention sweep has something real
    # to delete).
    seeded_paths = []
    for ts in ("2025-01-01T00:00:00.000000Z",
               "2025-02-01T00:00:00.000000Z",
               "2025-03-01T00:00:00.000000Z"):
        path = storage_dir / f"old-{ts}.tar"
        path.write_bytes(b"seed")
        seeded_paths.append(path)
        storage.record_snapshot(
            "srv_b3",
            {
                "configId": cfg["id"],
                "type": "backup",
                "createdAt": ts,
                "filePath": str(path),
                "fileName": path.name,
                "sizeBytes": 4,
                "status": "success",
            },
        )

    registry, _ = _fake_registry(install, running=False)
    monkeypatch.setattr(
        service, "get_server_process_registry", lambda: registry
    )

    service.run_backup(cfg["id"], trigger="manual")

    # After the run we have 4 total backups; max=2 means 2 are kept.
    snapshots = [
        s for s in storage.list_snapshots("srv_b3", config_id=cfg["id"])
        if s["type"] == "backup"
    ]
    assert len(snapshots) == 2
    # The two oldest seed files should have been deleted from disk.
    surviving_on_disk = [p for p in seeded_paths if p.exists()]
    assert len(surviving_on_disk) <= 1


def test_exclusions_are_honoured_in_archive(
    backups_env, monkeypatch, tmp_path
):
    storage = backups_env["storage"]
    service = backups_env["service"]
    tmp = backups_env["tmp"]

    install = _seed_server(tmp, "srv_b4")
    storage_dir = tmp_path / "store4"

    cfg = storage.create_config(
        "srv_b4",
        {
            "name": "Exclusions",
            "storagePath": str(storage_dir),
            "maxSnapshots": 0,
            "flush": False,
            "shutdown": False,
            "compress": False,
            "exclusions": ["logs/**"],
        },
    )

    registry, _ = _fake_registry(install, running=False)
    monkeypatch.setattr(
        service, "get_server_process_registry", lambda: registry
    )

    snapshot = service.run_backup(cfg["id"], trigger="manual")

    with tarfile.open(snapshot["filePath"], "r") as tf:
        names = set(tf.getnames())
    # logs/ was excluded; ``backups/`` would never appear (always-excluded).
    assert not any(name.startswith("logs/") or name == "logs" for name in names)
    assert any(name.startswith("world") for name in names)


def test_failure_records_error_snapshot_and_reraises(
    backups_env, monkeypatch, tmp_path
):
    storage = backups_env["storage"]
    service = backups_env["service"]
    tmp = backups_env["tmp"]

    install = _seed_server(tmp, "srv_b5")
    storage_dir = tmp_path / "store5"

    cfg = storage.create_config(
        "srv_b5",
        {
            "name": "Will fail",
            "storagePath": str(storage_dir),
            "maxSnapshots": 0,
            "compress": False,
        },
    )

    registry, _ = _fake_registry(install, running=False)
    monkeypatch.setattr(
        service, "get_server_process_registry", lambda: registry
    )

    def boom(*_a, **_kw):
        raise OSError("disk full")

    monkeypatch.setattr(service, "_copy_tree_with_exclusions", boom)

    with pytest.raises(OSError):
        service.run_backup(cfg["id"], trigger="manual")

    snapshots = storage.list_snapshots("srv_b5", config_id=cfg["id"])
    assert any(s["status"] == "error" for s in snapshots)


def test_adhoc_backup_creates_archive_with_null_config_id(
    backups_env, monkeypatch, tmp_path
):
    """Ad-hoc backup records configId=None and produces a real archive."""
    service = backups_env["service"]
    tmp = backups_env["tmp"]

    install = _seed_server(tmp, "srv_adhoc1")
    storage_dir = tmp_path / "adhoc-store"

    registry, _ = _fake_registry(install, running=False)
    monkeypatch.setattr(service, "get_server_process_registry", lambda: registry)

    snapshot = service.run_adhoc_backup(
        "srv_adhoc1",
        storage_path_str=str(storage_dir),
        compress=False,
        flush=False,
        shutdown=False,
    )

    assert snapshot["configId"] is None
    assert snapshot["status"] == "success"
    archive_path = Path(snapshot["filePath"])
    assert archive_path.exists()
    assert archive_path.parent == storage_dir
    with tarfile.open(archive_path, "r") as tf:
        names = tf.getnames()
    assert any(n.startswith("world") for n in names)


def test_adhoc_backup_async_returns_job_id(backups_env, monkeypatch, tmp_path):
    """run_adhoc_backup_async returns a bjb_ job id and seeds progress."""
    service = backups_env["service"]
    import backend.backups.progress as progress
    tmp = backups_env["tmp"]

    install = _seed_server(tmp, "srv_adhoc2")
    registry, _ = _fake_registry(install, running=False)
    monkeypatch.setattr(service, "get_server_process_registry", lambda: registry)

    job_id = service.run_adhoc_backup_async(
        "srv_adhoc2",
        storage_path_str=str(tmp_path / "adhoc2-store"),
        compress=False,
        flush=False,
        shutdown=False,
    )

    assert job_id.startswith("bjb_")
    state = progress.get(job_id)
    assert state["kind"] == "backup"
    assert state["config_id"] is None
