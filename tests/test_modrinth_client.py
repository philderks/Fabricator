"""Pin ModrinthClient class-level path-set invariants.

The two path-sets ``MODPACK_SWITCH_PATHS`` (sub-paths replaced by an
incoming modpack) and ``PROTECTED_SERVER_PATHS`` (never touched by a
switch) must be disjoint — otherwise a modpack-switch would silently
overwrite a protected directory like ``world`` or ``backups``.

The guard that consumed ``PROTECTED_SERVER_PATHS`` at runtime was
removed in an earlier cleanup; this test preserves the documentation
value of the constant by asserting the disjointness invariant.
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
