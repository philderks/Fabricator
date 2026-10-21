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

import subprocess
from unittest.mock import patch

import pytest

from backend.server.java_compat import max_java_for, resolve_required_java
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


# --- Max Java: legacy Forge crashes on Java that is too new ---------------


@pytest.mark.parametrize("mc, loader, expected", [
    ("1.7.10", "forge", 8),
    ("1.12.2", "Forge", 8),
    ("1.13.2", "forge", 11),
    ("1.16.5", "forge", 11),
    ("1.17.1", "forge", None),
    ("1.20.1", "forge", None),
    ("1.12.2", "vanilla", None),
    ("1.12.2", None, None),
    ("", "forge", None),
])
def test_max_java_for(mc, loader, expected):
    assert max_java_for(mc, loader) == expected


def _fake_java_run(system_major, managed_major=None):
    """``subprocess.run`` fake: PATH ``java`` is ``system_major``, any other path ``managed_major``."""
    def run(argv, **kwargs):
        major = system_major if argv[0] == "java" else managed_major
        if major is None:
            raise FileNotFoundError(argv[0])
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr=f'openjdk version "{major}.0.4"')
    return run


def _managed_path(tmp_path):
    return lambda major: tmp_path / "java" / str(major) / "bin" / "java"


def test_find_compatible_java_skips_too_new_system_java(tmp_path):
    from backend.server import java_manager
    with patch.object(java_manager, "_parse_system_java_major", return_value=21), \
            patch.object(java_manager, "managed_java_binary_path", _managed_path(tmp_path)):
        assert java_manager.find_compatible_java(8) == "java"
        assert java_manager.find_compatible_java(8, maximum=8) is None
        managed = _managed_path(tmp_path)(8)
        managed.parent.mkdir(parents=True)
        managed.touch()
        assert java_manager.find_compatible_java(8, maximum=8) == str(managed)


def test_legacy_forge_never_launches_on_too_new_path_java(tmp_path):
    """System Java 21 on PATH, Forge 1.12.2: report managed Java 8 missing, then use it once installed."""
    from backend.server import java_manager
    from backend.server.registry import ServerProcessRegistry
    registry = ServerProcessRegistry(tmp_path / "servers")
    server = {"id": "srv_forge", "version": "1.12.2", "loader": "forge", "installPath": "f", "memory": 2}
    managed = _managed_path(tmp_path)(8)

    with patch.object(java_manager, "managed_java_binary_path", _managed_path(tmp_path)), \
            patch("subprocess.run", side_effect=_fake_java_run(21)):
        missing = registry.get_java_runtime(server)
    assert missing["java_exec"] == str(managed)
    assert missing["java_missing"] is True

    managed.parent.mkdir(parents=True)
    managed.touch()
    with patch.object(java_manager, "managed_java_binary_path", _managed_path(tmp_path)), \
            patch("subprocess.run", side_effect=_fake_java_run(21, managed_major=8)):
        ready = registry.get_java_runtime(server)
    assert ready["java_exec"] == str(managed)
    assert ready["major_version"] == 8


def test_vanilla_still_uses_newer_path_java(tmp_path):
    from backend.server import java_manager
    from backend.server.registry import ServerProcessRegistry
    registry = ServerProcessRegistry(tmp_path / "servers")
    server = {"id": "srv_vanilla", "version": "1.12.2", "loader": "vanilla", "installPath": "v", "memory": 2}

    with patch.object(java_manager, "managed_java_binary_path", _managed_path(tmp_path)), \
            patch("subprocess.run", side_effect=_fake_java_run(21)):
        runtime = registry.get_java_runtime(server)
    assert runtime["java_exec"] == "java"
    assert runtime["major_version"] == 21
