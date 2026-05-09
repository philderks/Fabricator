"""Phase 3b.1 anchor tests — Forge legacy MC ranges resolve to Java 8.

These tests pin the end-to-end mapping that drives the Java-install modal
in the UI when a user creates a Forge 1.12.2 / 1.16.5 server. They live
in ``tests/`` (not at the repo root) so they're picked up by the default
``pytest`` run; the root-level ``test_java_compat.py`` is not in the
configured ``testpaths`` and only runs when invoked explicitly.

What we anchor:

1. The MC→Java map in ``backend.server.java_compat.resolve_required_java``
   returns Java 8 for the popular legacy Forge ranges (1.7.10, 1.12.2,
   1.16.5).
2. ``backend.server.java_manager.effective_install_major(8) == 8`` — Java
   8 is an Adoptium LTS release shipped directly, so no _MAJOR_FALLBACKS
   silent upgrade. The only existing fallback maps 16→17 because Adoptium
   doesn't ship Java 16.

Together these guarantee that the install-Java modal will be triggered
to download Adoptium Java 8 (not 11 / 17 / 21) when a user creates a
legacy Forge server. Actual modal-trigger UX remains a manual smoke test
per the Phase 3b.1 brief.
"""
from __future__ import annotations

from backend.server.java_compat import resolve_required_java
from backend.server.java_manager import effective_install_major


def test_forge_1_12_2_resolves_to_java_8_high_confidence():
    """Forge 1.12.2 (most popular legacy modpack target) needs Java 8."""
    compat = resolve_required_java("1.12.2")
    assert compat.required_java == 8
    assert compat.confidence == "high"
    assert compat.enforceable is True


def test_forge_1_16_5_resolves_to_java_8_high_confidence():
    """Forge 1.16.5 is the last MC version before the 1.17 modlauncher rewrite."""
    compat = resolve_required_java("1.16.5")
    assert compat.required_java == 8
    assert compat.confidence == "high"


def test_forge_1_7_10_resolves_to_java_8():
    """1.7.10 is the floor of the Forge promotions table."""
    assert resolve_required_java("1.7.10").required_java == 8


def test_java_8_install_major_has_no_fallback():
    """Java 8 is an Adoptium LTS release — no silent upgrade to 11/17/21."""
    assert effective_install_major(8) == 8
