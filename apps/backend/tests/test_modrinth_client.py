"""Pin ModrinthClient class-level path-set invariants.

The two path-sets ``MODPACK_SWITCH_PATHS`` (sub-paths replaced by an
incoming modpack) and ``PROTECTED_SERVER_PATHS`` (never touched by a
switch) must be disjoint — otherwise a modpack-switch would silently
overwrite a protected directory like ``world`` or ``backups``.

In addition, ``clean_modpack_switch_paths`` enforces a runtime guard
that skips ``PROTECTED_SERVER_PATHS`` entries even if a future caller
passes a widened path-set. Under shipped callers the guard is
unreachable (because of the disjointness above), but the contract is
exercised directly here via monkeypatch.
"""
from __future__ import annotations

from backend.modrinth.client import ModrinthClient


def test_modpack_switch_paths_and_protected_paths_are_disjoint():
    switchable = set(ModrinthClient.MODPACK_SWITCH_PATHS)
    protected = set(ModrinthClient.PROTECTED_SERVER_PATHS)
    overlap = switchable & protected
    assert not overlap, (
        f"MODPACK_SWITCH_PATHS overlaps PROTECTED_SERVER_PATHS: {overlap}. "
        "A modpack switch would silently overwrite a protected server path."
    )


def test_clean_modpack_switch_paths_guard_skips_protected_paths(tmp_path, monkeypatch):
    """The runtime guard skips PROTECTED_SERVER_PATHS entries even if
    MODPACK_SWITCH_PATHS is artificially widened to include them.

    Under shipped callers the two sets are disjoint (pinned by the test
    above), so this branch is unreachable from production code. The
    monkeypatch exercises the method-boundary contract directly — the
    guard is real, not theater.
    """
    (tmp_path / "mods").mkdir()
    (tmp_path / "mods" / "test.jar").write_text("x")
    (tmp_path / "world").mkdir()
    (tmp_path / "world" / "level.dat").write_text("savedata")

    client = ModrinthClient()
    monkeypatch.setattr(client, "MODPACK_SWITCH_PATHS", ("mods", "world"))

    removed = client.clean_modpack_switch_paths(tmp_path)

    assert "mods" in removed
    assert "world" not in removed
    assert not (tmp_path / "mods").exists()
    assert (tmp_path / "world" / "level.dat").read_text() == "savedata"
