"""Security + correctness tests for backend.server.players.files.

Covers:
  - path-traversal guard
  - atomic write roundtrip (whitelist/ops/bans)
  - missing-file → empty-list
  - transient JSONDecodeError retry
  - offline-UUID derivation (Java UUID.nameUUIDFromBytes equivalence)
"""
import json
import threading
import time
import uuid
from pathlib import Path

import pytest

from backend.server.players import files as players_files


# ---------- offline UUID ---------------------------------------------------

def _expected_offline_uuid(name: str) -> uuid.UUID:
    """Reference impl mirroring Java's UUID.nameUUIDFromBytes('OfflinePlayer:'+name)."""
    import hashlib
    md5 = hashlib.md5()
    md5.update(("OfflinePlayer:" + name).encode("utf-8"))
    digest = bytearray(md5.digest())
    digest[6] = (digest[6] & 0x0F) | 0x30  # version 3
    digest[8] = (digest[8] & 0x3F) | 0x80  # RFC 4122 variant
    return uuid.UUID(bytes=bytes(digest))


def test_offline_uuid_matches_minecraft_derivation():
    name = "Notch"
    assert players_files.offline_uuid(name) == _expected_offline_uuid(name)


def test_offline_uuid_is_stable_for_same_name():
    assert players_files.offline_uuid("Linus") == players_files.offline_uuid("Linus")


def test_offline_uuid_differs_per_name():
    assert players_files.offline_uuid("A") != players_files.offline_uuid("B")


# ---------- path traversal -------------------------------------------------

def test_read_rejects_path_traversal(tmp_path: Path):
    server_dir = tmp_path / "server"
    server_dir.mkdir()
    with pytest.raises(ValueError):
        players_files.read_json_list(server_dir, "../../etc/passwd")


def test_write_rejects_path_traversal(tmp_path: Path):
    server_dir = tmp_path / "server"
    server_dir.mkdir()
    with pytest.raises(ValueError):
        players_files.write_json_list(server_dir, "../escape.json", [])


def test_read_rejects_absolute_path_outside_server_dir(tmp_path: Path):
    server_dir = tmp_path / "server"
    server_dir.mkdir()
    with pytest.raises(ValueError):
        players_files.read_json_list(server_dir, "/etc/passwd")


# ---------- read/write roundtrip ------------------------------------------

def test_missing_file_returns_empty_list(tmp_path: Path):
    assert players_files.read_json_list(tmp_path, "whitelist.json") == []


def test_atomic_write_then_read_roundtrip(tmp_path: Path):
    entries = [{"uuid": "abc", "name": "Linus"}]
    players_files.write_json_list(tmp_path, "whitelist.json", entries)
    assert players_files.read_json_list(tmp_path, "whitelist.json") == entries


def test_write_creates_parent_dir_if_needed(tmp_path: Path):
    # Used for `.fabricator/uuid-cache.json` etc.
    players_files.write_json_list(tmp_path, ".fabricator/uuid-cache.json", [])
    assert (tmp_path / ".fabricator" / "uuid-cache.json").exists()


def test_write_is_atomic_no_partial_file_on_crash(tmp_path: Path, monkeypatch):
    """If the rename step is interrupted, the original file must be intact."""
    target = tmp_path / "whitelist.json"
    target.write_text(json.dumps([{"name": "original"}]))

    original_replace = Path.replace

    def boom(self, *args, **kwargs):
        raise OSError("simulated crash mid-rename")

    monkeypatch.setattr(Path, "replace", boom)
    with pytest.raises(OSError):
        players_files.write_json_list(tmp_path, "whitelist.json", [{"name": "new"}])

    # Original still readable, content unchanged.
    monkeypatch.setattr(Path, "replace", original_replace)
    assert players_files.read_json_list(tmp_path, "whitelist.json") == [{"name": "original"}]


# ---------- transient JSONDecodeError retry -------------------------------

def test_transient_json_decode_error_retried_once(tmp_path: Path, monkeypatch):
    target = tmp_path / "whitelist.json"
    # First read: invalid; second read: valid.
    target.write_text("{ not valid yet")

    call_count = {"n": 0}
    real_read_text = Path.read_text

    def flaky_read(self, *a, **kw):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return "{ not valid yet"
        return json.dumps([{"name": "after-retry"}])

    monkeypatch.setattr(Path, "read_text", flaky_read)
    monkeypatch.setattr(time, "sleep", lambda _: None)  # speed up test

    result = players_files.read_json_list(tmp_path, "whitelist.json")
    assert result == [{"name": "after-retry"}]
    assert call_count["n"] == 2  # one retry happened


def test_persistent_json_decode_error_raises(tmp_path: Path, monkeypatch):
    target = tmp_path / "whitelist.json"
    target.write_text("{ permanently broken")
    monkeypatch.setattr(time, "sleep", lambda _: None)
    with pytest.raises(json.JSONDecodeError):
        players_files.read_json_list(tmp_path, "whitelist.json")
