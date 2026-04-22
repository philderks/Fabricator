"""C2: Backup restore must be atomic — failure leaves the live tree intact.

Also covers M3: `_safe_extract_zip` must reject members whose resolved path
escapes the destination (the prior `startswith` check lets /var/lib/xy
through when destination is /var/lib/x).
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest


def test_safe_extract_zip_rejects_prefix_sibling_escape(tmp_path):
    """Destination is `x/`; a member that resolves to `xy/...` must be rejected.

    The legacy startswith check would wrongly allow this because the string
    "xy/..." starts with "x".
    """
    from backend.server.routes import _safe_extract_zip

    destination = tmp_path / "x"
    destination.mkdir()
    sibling = tmp_path / "xy"

    archive = tmp_path / "evil.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("../xy/evil.jar", b"pwn")

    with zipfile.ZipFile(archive, "r") as zf:
        with pytest.raises((ValueError, RuntimeError)):
            _safe_extract_zip(zf, destination)

    assert not (sibling / "evil.jar").exists()


def test_safe_extract_zip_rejects_absolute_path(tmp_path):
    """Members with absolute paths must not escape the destination."""
    from backend.server.routes import _safe_extract_zip

    destination = tmp_path / "x"
    destination.mkdir()

    archive = tmp_path / "evil.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("/tmp/escape.jar", b"pwn")

    with zipfile.ZipFile(archive, "r") as zf:
        with pytest.raises((ValueError, RuntimeError)):
            _safe_extract_zip(zf, destination)


def _seed_server(tmp_servers_root, populate_files=True):
    """Write a servers.json entry and optionally seed live files."""
    index = Path(tmp_servers_root) / "servers.json"
    index.write_text(
        json.dumps(
            [
                {
                    "id": "srv_restore",
                    "name": "Restore Test",
                    "version": "1.20.1",
                    "loader": "fabric",
                    "port": 25565,
                    "installPath": "srv_restore",
                    "status": "stopped",
                }
            ]
        ),
        encoding="utf-8",
    )
    install = Path(tmp_servers_root) / "servers" / "srv_restore"
    install.mkdir(parents=True, exist_ok=True)
    if populate_files:
        (install / "server.properties").write_text("port=25565\n", encoding="utf-8")
        (install / "world").mkdir(exist_ok=True)
        (install / "world" / "level.dat").write_text("LIVE-WORLD", encoding="utf-8")

    backups = install / "backups"
    backups.mkdir(exist_ok=True)
    return install, backups


def _write_good_backup(backups, name="good"):
    archive = backups / f"{name}.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("server.properties", "port=25566\n")
        zf.writestr("world/level.dat", "RESTORED-WORLD")
    return archive


def _write_broken_backup(backups, name="broken"):
    archive = backups / f"{name}.zip"
    archive.write_bytes(b"this is not a zip")
    return archive


def test_restore_good_backup_replaces_live_files(client, tmp_servers_root):
    install, backups = _seed_server(tmp_servers_root)
    _write_good_backup(backups, "good")

    resp = client.post("/api/servers/srv_restore/backups/good/restore")
    assert resp.status_code == 200, resp.get_json()

    assert (install / "world" / "level.dat").read_text() == "RESTORED-WORLD"
    assert "port=25566" in (install / "server.properties").read_text()


def test_restore_broken_backup_preserves_live_tree(client, tmp_servers_root):
    install, backups = _seed_server(tmp_servers_root)
    _write_broken_backup(backups, "broken")

    original_level = (install / "world" / "level.dat").read_text()

    resp = client.post("/api/servers/srv_restore/backups/broken/restore")
    assert resp.status_code in (400, 500), resp.get_json()

    assert (install / "world" / "level.dat").exists()
    assert (install / "world" / "level.dat").read_text() == original_level
    assert (install / "server.properties").read_text() == "port=25565\n"
    assert (backups / "broken.zip").exists()


def test_restore_keeps_backups_dir_during_swap(client, tmp_servers_root):
    install, backups = _seed_server(tmp_servers_root)
    _write_good_backup(backups, "good")

    resp = client.post("/api/servers/srv_restore/backups/good/restore")
    assert resp.status_code == 200
    assert (backups / "good.zip").exists()
