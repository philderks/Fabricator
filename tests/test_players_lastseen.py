"""Unit tests for backend.server.players.lastseen.

Covers:
  - level-name resolution: server.properties → config levelName → "world"
  - last-seen from playerdata mtime (.dat primary, .dat_old fallback)
  - uuid path-traversal guard
  - annotate_known_players enrichment (no input mutation)
"""
from __future__ import annotations

import os
from pathlib import Path

from backend.server.players import lastseen
from backend.utils.time import iso_z_from_timestamp


_UUID = "11111111-2222-3333-4444-555555555555"
_OLD_MTIME = 1_600_000_000  # 2020-09-13T12:26:40Z

# The two on-disk layouts the resolver probes.
_LAYOUTS = {
    "playerdata": ("playerdata",),        # classic (through 26.0)
    "players_data": ("players", "data"),  # 26.1+ save-format overhaul
}


def _make_playerdata(
    install: Path, level: str, uuid: str, suffix: str, mtime: int,
    layout: str = "playerdata",
) -> Path:
    pd = install.joinpath(level, *_LAYOUTS[layout])
    pd.mkdir(parents=True, exist_ok=True)
    f = pd / f"{uuid}.{suffix}"
    f.write_bytes(b"NBT")
    os.utime(f, (mtime, mtime))
    return f


# ---------- level-name resolution -----------------------------------------

def test_level_name_prefers_server_properties(tmp_path: Path):
    (tmp_path / "server.properties").write_text(
        "motd=hi\nlevel-name=testwelt\nonline-mode=true\n", encoding="utf-8"
    )
    assert lastseen.read_level_name(tmp_path, {"levelName": "configworld"}) == "testwelt"


def test_level_name_falls_back_to_config_when_properties_missing(tmp_path: Path):
    assert lastseen.read_level_name(tmp_path, {"levelName": "configworld"}) == "configworld"


def test_level_name_falls_back_to_config_when_key_absent(tmp_path: Path):
    (tmp_path / "server.properties").write_text("motd=hi\n", encoding="utf-8")
    assert lastseen.read_level_name(tmp_path, {"levelName": "configworld"}) == "configworld"


def test_level_name_defaults_to_world(tmp_path: Path):
    (tmp_path / "server.properties").write_text("level-name=   \n", encoding="utf-8")
    assert lastseen.read_level_name(tmp_path, {}) == "world"


def test_level_name_ignores_commented_key(tmp_path: Path):
    (tmp_path / "server.properties").write_text(
        "#level-name=commented\nlevel-name=real\n", encoding="utf-8"
    )
    assert lastseen.read_level_name(tmp_path, {}) == "real"


# ---------- last_seen_iso --------------------------------------------------

def test_last_seen_from_dat_mtime(tmp_path: Path):
    _make_playerdata(tmp_path, "world", _UUID, "dat", _OLD_MTIME)
    assert lastseen.last_seen_iso(tmp_path, "world", _UUID) == iso_z_from_timestamp(_OLD_MTIME)


def test_last_seen_falls_back_to_dat_old(tmp_path: Path):
    _make_playerdata(tmp_path, "world", _UUID, "dat_old", _OLD_MTIME)
    assert lastseen.last_seen_iso(tmp_path, "world", _UUID) == iso_z_from_timestamp(_OLD_MTIME)


def test_last_seen_prefers_dat_over_dat_old(tmp_path: Path):
    # max(mtime): the live .dat is the newer write in a normal rotation, so it
    # wins over the older .dat_old backup.
    _make_playerdata(tmp_path, "world", _UUID, "dat_old", _OLD_MTIME)
    newer = _OLD_MTIME + 5000
    _make_playerdata(tmp_path, "world", _UUID, "dat", newer)
    assert lastseen.last_seen_iso(tmp_path, "world", _UUID) == iso_z_from_timestamp(newer)


def test_last_seen_none_when_no_playerdata(tmp_path: Path):
    assert lastseen.last_seen_iso(tmp_path, "world", _UUID) is None


# ---------- probing: 26.1+ players/data layout + mixed inventory -----------

def test_last_seen_from_new_players_data_layout(tmp_path: Path):
    # 26.1+ stores the file at <level>/players/data/<uuid>.dat (no playerdata/).
    _make_playerdata(tmp_path, "world", _UUID, "dat", _OLD_MTIME, layout="players_data")
    assert lastseen.last_seen_iso(tmp_path, "world", _UUID) == iso_z_from_timestamp(_OLD_MTIME)


def test_last_seen_new_layout_dat_old_fallback(tmp_path: Path):
    _make_playerdata(tmp_path, "world", _UUID, "dat_old", _OLD_MTIME, layout="players_data")
    assert lastseen.last_seen_iso(tmp_path, "world", _UUID) == iso_z_from_timestamp(_OLD_MTIME)


def test_last_seen_max_across_mixed_layouts(tmp_path: Path):
    # A world upgraded across the 26.1 boundary can carry BOTH layouts. The
    # newest mtime wins regardless of which layout it lives in.
    legacy = _OLD_MTIME
    newer = _OLD_MTIME + 90_000
    _make_playerdata(tmp_path, "world", _UUID, "dat", legacy, layout="playerdata")
    _make_playerdata(tmp_path, "world", _UUID, "dat", newer, layout="players_data")
    assert lastseen.last_seen_iso(tmp_path, "world", _UUID) == iso_z_from_timestamp(newer)

    # And symmetric: if the legacy file is the newer one, it wins.
    newest = newer + 90_000
    _make_playerdata(tmp_path, "world", _UUID, "dat", newest, layout="playerdata")
    assert lastseen.last_seen_iso(tmp_path, "world", _UUID) == iso_z_from_timestamp(newest)


def test_last_seen_honours_custom_level_name(tmp_path: Path):
    _make_playerdata(tmp_path, "testwelt", _UUID, "dat", _OLD_MTIME)
    assert lastseen.last_seen_iso(tmp_path, "testwelt", _UUID) == iso_z_from_timestamp(_OLD_MTIME)
    # Wrong level name → nothing found.
    assert lastseen.last_seen_iso(tmp_path, "world", _UUID) is None


def test_last_seen_rejects_malformed_uuid(tmp_path: Path):
    # A path-traversal attempt in the uuid must never reach stat().
    assert lastseen.last_seen_iso(tmp_path, "world", "../../etc/passwd") is None
    assert lastseen.last_seen_iso(tmp_path, "world", "") is None
    assert lastseen.last_seen_iso(tmp_path, "world", "not-a-uuid") is None


# ---------- annotate_known_players ----------------------------------------

def test_annotate_adds_last_seen_and_preserves_entry(tmp_path: Path):
    _make_playerdata(tmp_path, "world", _UUID, "dat", _OLD_MTIME)
    known = [{"uuid": _UUID, "name": "Linus", "expiresOn": "2099-01-01 00:00:00 +0000"}]

    result = lastseen.annotate_known_players(tmp_path, {}, known)

    assert result[0]["lastSeen"] == iso_z_from_timestamp(_OLD_MTIME)
    assert result[0]["name"] == "Linus"
    # Original untouched (no lastSeen leaked into the on-disk list).
    assert "lastSeen" not in known[0]


def test_annotate_last_seen_none_for_never_joined(tmp_path: Path):
    known = [{"uuid": _UUID, "name": "GhostWhitelistOnly"}]
    result = lastseen.annotate_known_players(tmp_path, {}, known)
    assert result[0]["lastSeen"] is None


def test_annotate_uses_custom_level_name_from_properties(tmp_path: Path):
    (tmp_path / "server.properties").write_text("level-name=testwelt\n", encoding="utf-8")
    _make_playerdata(tmp_path, "testwelt", _UUID, "dat", _OLD_MTIME)
    result = lastseen.annotate_known_players(tmp_path, {"levelName": "ignored"}, [{"uuid": _UUID, "name": "L"}])
    assert result[0]["lastSeen"] == iso_z_from_timestamp(_OLD_MTIME)
