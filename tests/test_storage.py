"""C4: servers.json must be written atomically."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest


def test_save_servers_uses_temp_and_replace(tmp_servers_root):
    """save_servers must write to a temp file then atomically replace."""
    import importlib
    import backend.server.storage as storage
    importlib.reload(storage)

    captured_paths = []
    real_replace = __import__("os").replace

    def tracking_replace(src, dst):
        captured_paths.append((str(src), str(dst)))
        return real_replace(src, dst)

    payload = [{"id": "srv_abc", "name": "Demo"}]

    with patch("os.replace", side_effect=tracking_replace):
        storage.save_servers(payload)

    assert captured_paths, "save_servers did not call os.replace"
    src, dst = captured_paths[-1]
    assert src != dst, "os.replace src and dst should differ (temp->final)"
    assert dst.endswith("servers.json")

    # File content is the final payload.
    with open(dst, "r", encoding="utf-8") as fh:
        assert json.load(fh) == payload


def test_load_servers_raises_on_corrupt_file(tmp_servers_root):
    """Corrupt servers.json must not silently mask as empty list."""
    import importlib
    import backend.server.storage as storage
    importlib.reload(storage)

    Path(storage.SERVERS_FILE).write_text("{ not valid json", encoding="utf-8")

    with pytest.raises(json.JSONDecodeError):
        storage.load_servers()


def test_save_survives_simulated_crash_mid_write(tmp_servers_root, monkeypatch):
    """If os.replace is interrupted, previous servers.json is intact."""
    import importlib
    import backend.server.storage as storage
    importlib.reload(storage)

    storage.save_servers([{"id": "srv_original", "name": "Keep me"}])

    class BoomError(RuntimeError):
        pass

    def fail_replace(src, dst):  # noqa: ARG001
        raise BoomError("simulated crash between write and rename")

    monkeypatch.setattr("os.replace", fail_replace)

    with pytest.raises(BoomError):
        storage.save_servers([{"id": "srv_new", "name": "Should not land"}])

    # Previous file untouched.
    with open(storage.SERVERS_FILE, "r", encoding="utf-8") as fh:
        assert json.load(fh) == [{"id": "srv_original", "name": "Keep me"}]


def test_legacy_migration_does_not_destroy_source_file(tmp_path, monkeypatch):
    """Regression: the legacy-cwd migration must copy, not move.

    Before the fix, `_ensure_file_exists` did `shutil.move(legacy, configured)`.
    Tests run from the repo root with SERVER_INDEX_FILE pointed at a tmp path —
    so `legacy` resolved to the LIVE `servers.json` in the repo. Any test that
    triggered `_ensure_file_exists()` would silently move the user's live data
    into the tmp dir, which then got cleaned up. Catastrophic data loss.
    """
    import importlib
    import backend.server.storage as storage
    importlib.reload(storage)

    fake_repo = tmp_path / "repo"
    fake_repo.mkdir()
    legacy_path = fake_repo / "servers.json"
    legacy_path.write_text('[{"id": "srv_live", "name": "Live data"}]', encoding="utf-8")

    fresh_target = tmp_path / "configured" / "servers.json"
    monkeypatch.setenv("SERVER_INDEX_FILE", str(fresh_target))
    monkeypatch.chdir(fake_repo)

    storage._ensure_file_exists()

    assert legacy_path.exists(), (
        "Legacy servers.json was destroyed by the migration — "
        "must use copy2, not move"
    )
    assert fresh_target.exists(), "Migration should have populated the configured path"
    assert json.loads(legacy_path.read_text(encoding="utf-8")) == \
           json.loads(fresh_target.read_text(encoding="utf-8"))


def test_save_cleans_up_tmp_on_json_failure(tmp_servers_root, monkeypatch):
    """If json.dump raises, the tmp file must not be left behind."""
    import importlib
    import backend.server.storage as storage
    importlib.reload(storage)

    # An unserializable value — sets are not JSON-serializable.
    unserializable = [{"id": "srv_bad", "bad": {1, 2, 3}}]

    with pytest.raises(TypeError):
        storage.save_servers(unserializable)

    tmp_path = storage.SERVERS_FILE.with_suffix(
        storage.SERVERS_FILE.suffix + ".tmp"
    )
    assert not tmp_path.exists(), (
        f"Tmp file should have been cleaned up, but it still exists at {tmp_path}"
    )
