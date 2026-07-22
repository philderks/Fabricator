"""``get_java_runtime`` must probe the same freshly-resolved Java start uses.

``start_server`` already rebuilds the cached manager's command before every
launch ("Rebuild command so a freshly-installed managed Java is picked up
without requiring an explicit invalidate() between attempts",
registry.py) — so the LAUNCH path always sees a managed Java installed after
the manager was first cached. The guard probe (``get_java_runtime`` →
``probe_java``) historically did NOT rebuild: it probed the command built at
first touch (argv[0] ``'java'`` when no Java existed yet), so the install
route's Java guard kept returning 400 after a successful managed install
until process restart — the retry-400 loop from the C1/C2 smoke
(register #4).

These tests lock the fix: the guard probe rebuilds exactly like the launch
path, so guard truth and launch truth are the same ``command`` field by
construction. Cache semantics are preserved — the manager INSTANCE stays
cached (buffers, locks, process handle); only ``command`` refreshes, as it
always has on start.
"""
from __future__ import annotations

import subprocess
from unittest.mock import patch


MANAGED_PATH = "/managed/jdk-21/bin/java"


def _make_registry(base_dir):
    """Late import, upstream convention: ``test_app_factory`` wipes
    ``backend.*`` from ``sys.modules`` mid-session, so a module-level import
    here would keep referencing the pre-wipe module objects while
    ``mock.patch`` (string target) patches the post-wipe ones — the patch
    would be invisible to the registry. Importing at call time keeps both on
    the same module objects (same reason upstream tests import inside test
    bodies, e.g. test_install_java_pre_check)."""
    from backend.server.registry import ServerProcessRegistry
    return ServerProcessRegistry(base_dir)


def _server(**extra) -> dict:
    record = {
        "id": "srv_fresh",
        "name": "Freshness",
        "version": "1.21.4",
        "loader": "vanilla",
        "installPath": "srv-fresh",
        "memory": 2,
    }
    record.update(extra)
    return record


def _fake_run(system_major=None, other_major=None):
    """``subprocess.run`` fake discriminating on argv[0].

    ``system_major=None`` -> PATH ``java`` raises FileNotFoundError; any other
    binary path resolves to ``other_major`` (None -> FileNotFoundError too).
    """

    def run(argv, **kwargs):
        major = system_major if argv[0] == "java" else other_major
        if major is None:
            raise FileNotFoundError(argv[0])
        return subprocess.CompletedProcess(
            argv, 0, stdout="", stderr=f'openjdk version "{major}.0.4" 2024-07-16'
        )

    return run


def test_probe_sees_managed_java_installed_after_first_touch(tmp_path):
    """First touch caches 'java'; a later managed install must become visible."""
    registry = _make_registry(tmp_path)
    server = _server()

    # Phase A: no Java anywhere — first touch caches the manager with 'java'.
    with (
        patch("subprocess.run", side_effect=_fake_run()),
        patch(
            "backend.server.java_manager.find_compatible_java",
            return_value=None,
        ),
    ):
        first = registry.get_java_runtime(server)
    assert first["java_exec"] == "java"
    assert first["java_missing"] is True

    # Phase B: managed 21 has been installed (same process, same registry).
    with (
        patch("subprocess.run", side_effect=_fake_run(other_major=21)),
        patch(
            "backend.server.java_manager.find_compatible_java",
            return_value=MANAGED_PATH,
        ),
    ):
        second = registry.get_java_runtime(server)
    assert second["java_exec"] == MANAGED_PATH
    assert second["major_version"] == 21
    assert second["java_missing"] is False


def test_guard_and_launch_move_together(tmp_path):
    """Guard payload and launch argv[0] are the same freshly-built command."""
    registry = _make_registry(tmp_path)
    server = _server()

    with (
        patch("subprocess.run", side_effect=_fake_run()),
        patch(
            "backend.server.java_manager.find_compatible_java",
            return_value=None,
        ),
    ):
        registry.get_java_runtime(server)

    with (
        patch("subprocess.run", side_effect=_fake_run(other_major=21)),
        patch(
            "backend.server.java_manager.find_compatible_java",
            return_value=MANAGED_PATH,
        ),
    ):
        runtime = registry.get_java_runtime(server)

    manager = registry.get_manager("srv_fresh")
    assert runtime["java_exec"] == manager.command[0] == MANAGED_PATH


def test_java_present_at_first_touch_unchanged(tmp_path):
    """Fleet pin: Java staged before first touch — behavior byte-identical,
    and the manager INSTANCE stays cached across calls."""
    registry = _make_registry(tmp_path)
    server = _server()

    with (
        patch("subprocess.run", side_effect=_fake_run(other_major=21)),
        patch(
            "backend.server.java_manager.find_compatible_java",
            return_value=MANAGED_PATH,
        ),
    ):
        first = registry.get_java_runtime(server)
        manager_a = registry.get_manager("srv_fresh")
        second = registry.get_java_runtime(server)
        manager_b = registry.get_manager("srv_fresh")

    assert first["java_exec"] == second["java_exec"] == MANAGED_PATH
    assert first["major_version"] == second["major_version"] == 21
    assert manager_a is manager_b


def test_explicit_javapath_unaffected(tmp_path):
    """Explicit javaPath keeps start precedence 1: resolver never consulted."""
    registry = _make_registry(tmp_path)
    server = _server(javaPath="/custom/java")

    with (
        patch("subprocess.run", side_effect=_fake_run(other_major=21)),
        patch(
            "backend.server.java_manager.find_compatible_java",
            return_value=MANAGED_PATH,
        ) as find_mock,
    ):
        first = registry.get_java_runtime(server)
        second = registry.get_java_runtime(server)

    find_mock.assert_not_called()
    assert first["java_exec"] == second["java_exec"] == "/custom/java"
    assert first["major_version"] == 21
