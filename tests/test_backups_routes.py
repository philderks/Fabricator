"""Backup-manager HTTP surface (``backend.backups.routes``).

Pins:
- The legacy ``/api/servers/<id>/backup`` and friends are GONE (404 now).
- ``DELETE /backup-configs/<id>`` without ``?purge=1`` retains archives
  on disk AND surfaces them in the response (no silent orphans).
- ``DELETE /backup-configs/<id>?purge=1`` deletes archive files that
  live inside the config's ``storagePath``.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture
def env(tmp_servers_root, monkeypatch):
    monkeypatch.setenv("BACKUPS_DIR", str(tmp_servers_root / "backups-route"))
    monkeypatch.setenv("FABRICATOR_DISABLE_SCHEDULER", "1")

    import importlib
    import backend.backups.storage as bs
    import backend.backups.scheduler as bsch
    import backend.backups.service as bsvc
    import backend.backups.restore as brst
    import backend.backups.routes as br
    importlib.reload(bs)
    importlib.reload(bsch)
    importlib.reload(bsvc)
    importlib.reload(brst)
    importlib.reload(br)
    bs.reset_for_tests()
    yield {"storage": bs, "tmp": Path(tmp_servers_root)}
    bs.reset_for_tests()


def _seed_server(tmp_root: Path, server_id: str):
    index = tmp_root / "servers.json"
    index.write_text(
        json.dumps(
            [
                {
                    "id": server_id,
                    "name": "X",
                    "version": "1.20.1",
                    "loader": "fabric",
                    "port": 25565,
                    "installPath": server_id,
                    "status": "stopped",
                }
            ]
        ),
        encoding="utf-8",
    )
    install = tmp_root / "servers" / server_id
    install.mkdir(parents=True, exist_ok=True)
    return install


def test_legacy_backup_endpoints_removed(client, tmp_servers_root):
    """The legacy backup routes must no longer be registered."""
    _seed_server(Path(tmp_servers_root), "srv_legacy")

    for path in (
        "/api/servers/srv_legacy/backups",
        "/api/servers/srv_legacy/backup",
        "/api/servers/srv_legacy/backups/some/restore",
        "/api/servers/srv_legacy/backups/some",
    ):
        method = (
            "POST" if path.endswith("/backup") or path.endswith("/restore")
            else "GET" if path.endswith("/backups") else "DELETE"
        )
        resp = client.open(path, method=method)
        # 404 (or 405 for the wrong verb) — never 200/202.
        assert resp.status_code in (404, 405), (
            f"Legacy endpoint {method} {path} still wired: {resp.status_code}"
        )


def test_create_list_and_run_config(client, env):
    _seed_server(env["tmp"], "srv_routes")

    create = client.post(
        "/api/servers/srv_routes/backup-configs",
        json={
            "name": "Daily",
            "storagePath": str(env["tmp"] / "store"),
            "maxSnapshots": 0,
            "schedule": {
                "enabled": False,
                "frequencyHours": 24,
                "timeOfDay": "03:00",
            },
        },
    )
    assert create.status_code == 201, create.get_json()
    cfg = create.get_json()

    listing = client.get("/api/servers/srv_routes/backup-configs").get_json()
    assert len(listing) == 1
    assert listing[0]["id"] == cfg["id"]

    summary = client.get(
        "/api/servers/srv_routes/backup-summary"
    ).get_json()
    assert summary["total_snapshots"] == 0
    assert summary["configs_count"] == 1


def test_delete_config_without_purge_retains_files(client, env, monkeypatch):
    """No-purge delete must retain archives AND surface them in the response."""
    storage_dir = env["tmp"] / "purge-store"
    storage_dir.mkdir()
    _seed_server(env["tmp"], "srv_no_purge")

    storage = env["storage"]
    cfg = storage.create_config(
        "srv_no_purge",
        {
            "name": "Keepers",
            "storagePath": str(storage_dir),
        },
    )
    archive = storage_dir / "old.tar"
    archive.write_bytes(b"archive")
    storage.record_snapshot(
        "srv_no_purge",
        {
            "configId": cfg["id"],
            "type": "backup",
            "filePath": str(archive),
            "fileName": "old.tar",
            "sizeBytes": archive.stat().st_size,
            "status": "success",
        },
    )

    resp = client.delete(
        f"/api/servers/srv_no_purge/backup-configs/{cfg['id']}"
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["deleted_files"] == 0
    assert str(archive) in body["retained_paths"]
    # File still on disk — no silent orphans.
    assert archive.exists()


def test_delete_config_with_purge_unlinks_files(client, env):
    storage_dir = env["tmp"] / "purge-yes"
    storage_dir.mkdir()
    _seed_server(env["tmp"], "srv_purge")

    storage = env["storage"]
    cfg = storage.create_config(
        "srv_purge",
        {"name": "Purgeables", "storagePath": str(storage_dir)},
    )
    archive = storage_dir / "old.tar"
    archive.write_bytes(b"archive")
    storage.record_snapshot(
        "srv_purge",
        {
            "configId": cfg["id"],
            "type": "backup",
            "filePath": str(archive),
            "fileName": "old.tar",
            "sizeBytes": archive.stat().st_size,
            "status": "success",
        },
    )

    resp = client.delete(
        f"/api/servers/srv_purge/backup-configs/{cfg['id']}?purge=1"
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["deleted_files"] == 1
    assert not archive.exists()


def test_delete_config_purge_only_inside_storage_path(client, env):
    """Files OUTSIDE the config's storagePath must never be deleted."""
    inside = env["tmp"] / "inside-store"
    inside.mkdir()
    outside = env["tmp"] / "outside-store"
    outside.mkdir()
    _seed_server(env["tmp"], "srv_outside")

    storage = env["storage"]
    cfg = storage.create_config(
        "srv_outside",
        {"name": "Defensive", "storagePath": str(inside)},
    )
    # Two records: one inside, one outside.
    inside_archive = inside / "a.tar"
    inside_archive.write_bytes(b"a")
    outside_archive = outside / "b.tar"
    outside_archive.write_bytes(b"b")
    for path in (inside_archive, outside_archive):
        storage.record_snapshot(
            "srv_outside",
            {
                "configId": cfg["id"],
                "type": "backup",
                "filePath": str(path),
                "fileName": path.name,
                "sizeBytes": path.stat().st_size,
                "status": "success",
            },
        )

    resp = client.delete(
        f"/api/servers/srv_outside/backup-configs/{cfg['id']}?purge=1"
    )
    body = resp.get_json()
    assert body["deleted_files"] == 1
    assert body["retained_files"] == 1
    assert str(outside_archive) in body["retained_paths"]
    assert not inside_archive.exists()
    assert outside_archive.exists()


def test_restore_invalid_mode_returns_400(client, env):
    storage_dir = env["tmp"] / "mode-store"
    storage_dir.mkdir()
    _seed_server(env["tmp"], "srv_mode")

    storage = env["storage"]
    cfg = storage.create_config(
        "srv_mode",
        {"name": "M", "storagePath": str(storage_dir)},
    )
    archive = storage_dir / "x.tar"
    archive.write_bytes(b"x")
    snap = storage.record_snapshot(
        "srv_mode",
        {
            "configId": cfg["id"],
            "type": "backup",
            "filePath": str(archive),
            "fileName": "x.tar",
            "sizeBytes": archive.stat().st_size,
            "status": "success",
        },
    )

    resp = client.post(
        f"/api/servers/srv_mode/snapshots/{snap['id']}/restore",
        json={"mode": "nope"},
    )
    assert resp.status_code == 400


def test_backup_jobs_polling_returns_404_for_unknown(client, env):
    resp = client.get("/api/backup-jobs/bjr_does_not_exist")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Quick backup (config-free)
# ---------------------------------------------------------------------------


def test_quick_backup_returns_202_with_job_id(client, env, monkeypatch, tmp_path):
    """POST /backup-quick with a valid storagePath returns 202 + job_id."""
    import backend.backups.service as svc

    _seed_server(env["tmp"], "srv_quick1")

    from unittest.mock import MagicMock
    fake_registry = MagicMock()
    fake_registry.resolve_install_path.return_value = env["tmp"] / "servers" / "srv_quick1"
    fake_registry.get_status.return_value = {"status": "stopped"}
    fake_registry.get_manager.return_value = None
    monkeypatch.setattr(svc, "get_server_process_registry", lambda: fake_registry)

    resp = client.post(
        "/api/servers/srv_quick1/backup-quick",
        json={
            "storagePath": str(tmp_path / "quick-store"),
            "compress": False,
            "flush": False,
            "shutdown": False,
        },
    )
    assert resp.status_code == 202, resp.get_json()
    body = resp.get_json()
    assert body["success"] is True
    assert body["job_id"].startswith("bjb_")


def test_quick_backup_omitting_storage_path_uses_default(client, env, monkeypatch, tmp_path):
    """Omitting storagePath is valid — backend falls back to <install>/backups."""
    import backend.backups.service as svc

    _seed_server(env["tmp"], "srv_quick2")

    from unittest.mock import MagicMock
    fake_registry = MagicMock()
    fake_registry.resolve_install_path.return_value = env["tmp"] / "servers" / "srv_quick2"
    fake_registry.get_status.return_value = {"status": "stopped"}
    fake_registry.get_manager.return_value = None
    monkeypatch.setattr(svc, "get_server_process_registry", lambda: fake_registry)

    resp = client.post(
        "/api/servers/srv_quick2/backup-quick",
        json={"compress": True},
    )
    assert resp.status_code == 202, resp.get_json()
    assert resp.get_json()["job_id"].startswith("bjb_")


def test_quick_backup_unknown_server_returns_404(client, env):
    """Unknown server_id must yield 404 via @require_server."""
    resp = client.post(
        "/api/servers/srv_does_not_exist/backup-quick",
        json={"storagePath": "/tmp/x"},
    )
    assert resp.status_code == 404
