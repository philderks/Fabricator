"""Per-server JSON storage for backup configs + snapshot history.

Pins:
- Round-trip create/update/delete for configs and snapshots.
- Per-server isolation (one server's file isn't read for another).
- Atomic save semantics (tmp + os.replace).
- Lookup index (config_id / snapshot_id -> server_id) walks all files
  AND survives create/delete invalidation.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from unittest.mock import patch

import pytest


_ISO_Z_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{6})?Z")


@pytest.fixture
def backups_storage(tmp_servers_root, monkeypatch):
    """Reload the storage module against a tmp BACKUPS_DIR.

    Mirrors the ``tmp_servers_root`` pattern from ``conftest.py`` so the
    backup file path is fully overridden via env. Returns the module.
    """
    monkeypatch.setenv("BACKUPS_DIR", str(tmp_servers_root / "backups"))
    import importlib
    import backend.backups.storage as storage
    importlib.reload(storage)
    storage.reset_for_tests()
    yield storage
    storage.reset_for_tests()


def test_create_and_list_config_roundtrip(backups_storage):
    storage = backups_storage

    record = storage.create_config(
        "srv_a",
        {
            "name": "Daily",
            "storagePath": "/tmp/backups-a",
            "maxSnapshots": 5,
            "flush": True,
            "shutdown": False,
            "compress": True,
            "exclusions": ["logs/**"],
            "schedule": {
                "enabled": True,
                "frequencyHours": 24,
                "timeOfDay": "03:00",
            },
        },
    )

    assert record["id"].startswith("bkc_")
    assert record["serverId"] == "srv_a"
    assert record["name"] == "Daily"
    assert _ISO_Z_RE.fullmatch(record["createdAt"])
    assert _ISO_Z_RE.fullmatch(record["updatedAt"])

    configs = storage.list_configs("srv_a")
    assert len(configs) == 1
    assert configs[0]["id"] == record["id"]


def test_update_config_preserves_fields_not_in_payload(backups_storage):
    storage = backups_storage
    record = storage.create_config(
        "srv_a", {"name": "Daily", "storagePath": "/tmp/a", "maxSnapshots": 7}
    )

    updated = storage.update_config(
        "srv_a", record["id"], {"name": "Renamed Daily"}
    )
    assert updated is not None
    assert updated["name"] == "Renamed Daily"
    # Unrelated fields preserved.
    assert updated["maxSnapshots"] == 7
    assert updated["storagePath"] == "/tmp/a"
    assert updated["updatedAt"] >= record["updatedAt"]


def test_delete_config_returns_snapshots_and_drops_records(backups_storage):
    storage = backups_storage
    cfg = storage.create_config(
        "srv_a", {"name": "X", "storagePath": "/tmp/x"}
    )
    storage.record_snapshot(
        "srv_a",
        {
            "configId": cfg["id"],
            "type": "backup",
            "filePath": "/tmp/x/a.tar",
            "fileName": "a.tar",
            "sizeBytes": 100,
            "status": "success",
        },
    )
    storage.record_snapshot(
        "srv_a",
        {
            "configId": cfg["id"],
            "type": "backup",
            "filePath": "/tmp/x/b.tar",
            "fileName": "b.tar",
            "sizeBytes": 100,
            "status": "success",
        },
    )

    result = storage.delete_config("srv_a", cfg["id"])
    assert result is not None
    removed_config, removed_snapshots = result
    assert removed_config["id"] == cfg["id"]
    assert len(removed_snapshots) == 2

    assert storage.list_configs("srv_a") == []
    assert storage.list_snapshots("srv_a") == []


def test_per_server_isolation(backups_storage):
    storage = backups_storage
    cfg_a = storage.create_config(
        "srv_a", {"name": "A", "storagePath": "/tmp/a"}
    )
    cfg_b = storage.create_config(
        "srv_b", {"name": "B", "storagePath": "/tmp/b"}
    )

    assert [c["id"] for c in storage.list_configs("srv_a")] == [cfg_a["id"]]
    assert [c["id"] for c in storage.list_configs("srv_b")] == [cfg_b["id"]]


def test_save_uses_tmp_and_replace(backups_storage):
    storage = backups_storage

    captured_paths = []
    real_replace = os.replace

    def tracking_replace(src, dst):
        captured_paths.append((str(src), str(dst)))
        return real_replace(src, dst)

    with patch("backend.backups.storage.os.replace", side_effect=tracking_replace):
        storage.create_config("srv_z", {"name": "Z", "storagePath": "/tmp/z"})

    assert captured_paths, "create_config did not call os.replace"
    src, dst = captured_paths[-1]
    assert src != dst
    assert dst.endswith("srv_z.json")
    with open(dst, "r", encoding="utf-8") as fh:
        payload = json.load(fh)
    assert len(payload["configs"]) == 1
    assert payload["configs"][0]["name"] == "Z"


def test_lookup_index_walks_all_files_then_invalidates(backups_storage):
    storage = backups_storage
    cfg_a = storage.create_config(
        "srv_a", {"name": "A", "storagePath": "/tmp/a"}
    )
    cfg_b = storage.create_config(
        "srv_b", {"name": "B", "storagePath": "/tmp/b"}
    )

    assert storage.lookup_server_for_config(cfg_a["id"]) == "srv_a"
    assert storage.lookup_server_for_config(cfg_b["id"]) == "srv_b"

    # Delete and confirm the cache is invalidated.
    storage.delete_config("srv_a", cfg_a["id"])
    assert storage.lookup_server_for_config(cfg_a["id"]) is None
    assert storage.lookup_server_for_config(cfg_b["id"]) == "srv_b"


def test_record_and_list_snapshots_sorted_newest_first(backups_storage):
    storage = backups_storage
    cfg = storage.create_config(
        "srv_a", {"name": "A", "storagePath": "/tmp/a"}
    )
    s1 = storage.record_snapshot(
        "srv_a",
        {
            "configId": cfg["id"],
            "type": "backup",
            "createdAt": "2025-01-01T00:00:00.000000Z",
            "filePath": "/tmp/a/1.tar",
            "fileName": "1.tar",
            "sizeBytes": 100,
            "status": "success",
        },
    )
    s2 = storage.record_snapshot(
        "srv_a",
        {
            "configId": cfg["id"],
            "type": "backup",
            "createdAt": "2025-02-01T00:00:00.000000Z",
            "filePath": "/tmp/a/2.tar",
            "fileName": "2.tar",
            "sizeBytes": 200,
            "status": "success",
        },
    )

    snapshots = storage.list_snapshots("srv_a")
    assert [s["id"] for s in snapshots] == [s2["id"], s1["id"]]


def test_delete_snapshot_record(backups_storage):
    storage = backups_storage
    cfg = storage.create_config(
        "srv_a", {"name": "A", "storagePath": "/tmp/a"}
    )
    snap = storage.record_snapshot(
        "srv_a",
        {
            "configId": cfg["id"],
            "type": "backup",
            "filePath": "/tmp/a/x.tar",
            "fileName": "x.tar",
            "sizeBytes": 1,
            "status": "success",
        },
    )

    assert storage.delete_snapshot_record("srv_a", snap["id"]) is True
    assert storage.delete_snapshot_record("srv_a", snap["id"]) is False
    assert storage.list_snapshots("srv_a") == []


def test_delete_server_file_removes_json(backups_storage, tmp_servers_root):
    storage = backups_storage
    storage.create_config("srv_a", {"name": "A", "storagePath": "/tmp/a"})

    file_path = Path(tmp_servers_root) / "backups" / "srv_a.json"
    assert file_path.exists()

    assert storage.delete_server_file("srv_a") is True
    assert not file_path.exists()
    assert storage.delete_server_file("srv_a") is False
