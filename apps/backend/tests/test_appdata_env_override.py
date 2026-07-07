"""Pin FABRICATOR_APPDATA env-override behaviour for appdata_dir().

The override exists so tests and non-default installs can redirect the
data directory without monkey-patching HOME or APPDATA. The function is
``@lru_cache``'d, so each test clears the cache before reading.
"""
from __future__ import annotations

from pathlib import Path

from backend.utils.platform import appdata_dir


def test_fabricator_appdata_env_override_takes_precedence(monkeypatch, tmp_path):
    override_dir = tmp_path / "custom-appdata"
    monkeypatch.setenv("FABRICATOR_APPDATA", str(override_dir))
    appdata_dir.cache_clear()
    assert appdata_dir() == override_dir
    assert override_dir.is_dir()


def test_fabricator_appdata_creates_missing_directory(monkeypatch, tmp_path):
    nested = tmp_path / "a" / "b" / "c"
    assert not nested.exists()
    monkeypatch.setenv("FABRICATOR_APPDATA", str(nested))
    appdata_dir.cache_clear()
    result = appdata_dir()
    assert result == nested
    assert nested.is_dir()


def test_fabricator_appdata_expands_tilde(monkeypatch, tmp_path):
    # ``Path.expanduser`` reads HOME on POSIX and USERPROFILE on Windows.
    # The Windows-bundled deployment target makes the USERPROFILE leg
    # non-theoretical — set both so the expansion is deterministic across
    # platforms.
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("FABRICATOR_APPDATA", "~/sentinel-appdata")
    appdata_dir.cache_clear()
    result = appdata_dir()
    assert result == tmp_path / "sentinel-appdata"
    assert result.is_dir()
