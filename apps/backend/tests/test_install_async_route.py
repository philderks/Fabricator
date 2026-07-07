"""Concurrency tests for the async install_server route.

The route spawns a daemon thread that runs the installer with progress
callbacks. The lock acquired by the route survives the route's return
because the thread's closure holds a reference; the thread releases it
in `finally`. These tests pin the lock-and-thread semantics.
"""
from __future__ import annotations

import importlib
import time
import threading
from unittest.mock import patch

from backend.server.installer.base import InstallResult, InstallStatus, LaunchSpec


def _install_progress_module():
    """Look up the install_progress module via importlib.

    test_app_factory.py reloads ``backend.*`` modules, which means a top-
    level ``from backend.server import install_progress`` would hold the
    pre-reload module while the route holds the post-reload one — they
    have different ``_store`` dicts. ``importlib.import_module`` always
    returns whatever sys.modules currently has, so this stays in sync
    with the route's view of the world.
    """
    return importlib.import_module("backend.server.install_progress")


def _seed(tmp_servers_root, sid_suffix: str = "1"):
    """Seed a Fabric server. tmp_servers_root ensures isolation across tests."""
    from backend.server import storage
    server = storage.create_server({
        "name": f"AsyncTest-{sid_suffix}",
        "version": "1.21.4",
        "loader": "fabric",
        "port": 25500 + int(sid_suffix),
        "installPath": f"async-test-{sid_suffix}",
        "memory": 2,
    })
    return server


def _wait(server_id: str, timeout: float = 5.0) -> dict:
    deadline = time.time() + timeout
    ip = _install_progress_module()
    while time.time() < deadline:
        entry = ip.get(server_id)
        if entry.get('phase') in ('done', 'failed'):
            return entry
        time.sleep(0.01)
    raise AssertionError(f"timeout: {ip.get(server_id)!r}")


def test_install_returns_202_with_initial_progress(client, tmp_servers_root):
    server = _seed(tmp_servers_root)
    server_id = server["id"]
    _install_progress_module().clear(server_id)

    fake_result = InstallResult(
        success=True, status=InstallStatus.COMPLETED, message="ok",
        launch=LaunchSpec(type="jar", jar="server.jar", program_args=["nogui"]),
    )

    with patch.dict("os.environ", {"FABRICATOR_SKIP_JAVA_CHECK": "1"}), \
         patch("backend.server.installer.fabric.FabricInstaller.install_with_config",
               return_value=fake_result):
        resp = client.post(f"/api/servers/{server_id}/install")

        assert resp.status_code == 202
        body = resp.get_json()
        assert body["active"] is True
        assert body["phase"] == "starting"
        assert body["server_id"] == server_id

        # Wait for thread to finish so the registry lock is released for other tests.
        _wait(server_id)


def test_double_install_returns_409_while_first_is_running(client, tmp_servers_root):
    """Two concurrent POST /install on the same server: second gets 409."""
    server = _seed(tmp_servers_root)
    server_id = server["id"]
    _install_progress_module().clear(server_id)

    # Install_with_config blocks on a barrier so we can fire a second POST
    # while the first thread is still holding the lock.
    block_event = threading.Event()
    release_event = threading.Event()

    def slow_install(*args, **kwargs):
        block_event.set()
        release_event.wait(timeout=5.0)
        return InstallResult(
            success=True, status=InstallStatus.COMPLETED, message="ok",
            launch=LaunchSpec(type="jar", jar="server.jar", program_args=["nogui"]),
        )

    with patch.dict("os.environ", {"FABRICATOR_SKIP_JAVA_CHECK": "1"}), \
         patch("backend.server.installer.fabric.FabricInstaller.install_with_config",
               side_effect=slow_install):
        resp1 = client.post(f"/api/servers/{server_id}/install")
        assert resp1.status_code == 202

        # Wait for the first thread to actually be inside the installer.
        assert block_event.wait(timeout=2.0), "first install did not enter installer"

        resp2 = client.post(f"/api/servers/{server_id}/install")
        assert resp2.status_code == 409
        body = resp2.get_json()
        assert "in progress" in body["error"].lower()

        # Let the first install finish.
        release_event.set()
        _wait(server_id)


def test_lock_released_after_done(client, tmp_servers_root):
    """After phase=done, a second install on the same server succeeds (lock released)."""
    server = _seed(tmp_servers_root)
    server_id = server["id"]
    _install_progress_module().clear(server_id)

    fake_result = InstallResult(
        success=True, status=InstallStatus.COMPLETED, message="ok",
        launch=LaunchSpec(type="jar", jar="server.jar", program_args=["nogui"]),
    )

    with patch.dict("os.environ", {"FABRICATOR_SKIP_JAVA_CHECK": "1"}), \
         patch("backend.server.installer.fabric.FabricInstaller.install_with_config",
               return_value=fake_result):
        resp1 = client.post(f"/api/servers/{server_id}/install")
        assert resp1.status_code == 202
        _wait(server_id)

        resp2 = client.post(f"/api/servers/{server_id}/install")
        assert resp2.status_code == 202  # would be 409 if lock leaked
        _wait(server_id)


def test_lock_released_after_failed(client, tmp_servers_root):
    """After phase=failed, a second install succeeds (lock released)."""
    server = _seed(tmp_servers_root)
    server_id = server["id"]
    _install_progress_module().clear(server_id)

    failure = InstallResult(
        success=False, status=InstallStatus.FAILED, message="simulated failure",
    )

    with patch.dict("os.environ", {"FABRICATOR_SKIP_JAVA_CHECK": "1"}), \
         patch("backend.server.installer.fabric.FabricInstaller.install_with_config",
               return_value=failure):
        resp1 = client.post(f"/api/servers/{server_id}/install")
        assert resp1.status_code == 202
        final = _wait(server_id)
        assert final["phase"] == "failed"

        # Lock is released — second install can be initiated.
        resp2 = client.post(f"/api/servers/{server_id}/install")
        assert resp2.status_code == 202
        _wait(server_id)


def test_lock_released_after_installer_exception(client, tmp_servers_root):
    """If the installer raises, the lock must still be released and progress shows 'failed'."""
    server = _seed(tmp_servers_root)
    server_id = server["id"]
    _install_progress_module().clear(server_id)

    with patch.dict("os.environ", {"FABRICATOR_SKIP_JAVA_CHECK": "1"}), \
         patch("backend.server.installer.fabric.FabricInstaller.install_with_config",
               side_effect=RuntimeError("installer exploded")):
        resp1 = client.post(f"/api/servers/{server_id}/install")
        assert resp1.status_code == 202
        final = _wait(server_id)
        assert final["phase"] == "failed"
        assert "installer exploded" in final["error"] or "Installation crashed" in final["error"]

        resp2 = client.post(f"/api/servers/{server_id}/install")
        assert resp2.status_code == 202
        _wait(server_id)


def test_get_progress_shows_active_during_install(client, tmp_servers_root):
    server = _seed(tmp_servers_root)
    server_id = server["id"]
    _install_progress_module().clear(server_id)

    block_event = threading.Event()
    release_event = threading.Event()

    def slow_install(*args, **kwargs):
        block_event.set()
        release_event.wait(timeout=5.0)
        return InstallResult(
            success=True, status=InstallStatus.COMPLETED, message="ok",
            launch=LaunchSpec(type="jar", jar="server.jar", program_args=["nogui"]),
        )

    with patch.dict("os.environ", {"FABRICATOR_SKIP_JAVA_CHECK": "1"}), \
         patch("backend.server.installer.fabric.FabricInstaller.install_with_config",
               side_effect=slow_install):
        resp_post = client.post(f"/api/servers/{server_id}/install")
        assert resp_post.status_code == 202
        block_event.wait(timeout=2.0)

        resp_get = client.get(f"/api/servers/{server_id}/install/progress")
        assert resp_get.status_code == 200
        body = resp_get.get_json()
        assert body["active"] is True
        # phase is in {'starting', ... up to whatever the installer is doing}
        assert "phase" in body

        release_event.set()
        _wait(server_id)


def test_get_progress_after_done_shows_inactive(client, tmp_servers_root):
    server = _seed(tmp_servers_root)
    server_id = server["id"]
    _install_progress_module().clear(server_id)

    fake_result = InstallResult(
        success=True, status=InstallStatus.COMPLETED, message="ok",
        launch=LaunchSpec(type="jar", jar="server.jar", program_args=["nogui"]),
    )

    with patch.dict("os.environ", {"FABRICATOR_SKIP_JAVA_CHECK": "1"}), \
         patch("backend.server.installer.fabric.FabricInstaller.install_with_config",
               return_value=fake_result):
        client.post(f"/api/servers/{server_id}/install")
        _wait(server_id)

    resp = client.get(f"/api/servers/{server_id}/install/progress")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["active"] is False
    assert body["phase"] == "done"


def test_two_servers_install_in_parallel(client, tmp_servers_root):
    """Lock is per-server-id; two different servers can install concurrently."""
    server_a = _seed(tmp_servers_root, "1")
    server_b = _seed(tmp_servers_root, "2")
    _install_progress_module().clear(server_a["id"])
    _install_progress_module().clear(server_b["id"])

    fake_result = InstallResult(
        success=True, status=InstallStatus.COMPLETED, message="ok",
        launch=LaunchSpec(type="jar", jar="server.jar", program_args=["nogui"]),
    )

    with patch.dict("os.environ", {"FABRICATOR_SKIP_JAVA_CHECK": "1"}), \
         patch("backend.server.installer.fabric.FabricInstaller.install_with_config",
               return_value=fake_result):
        resp_a = client.post(f"/api/servers/{server_a['id']}/install")
        resp_b = client.post(f"/api/servers/{server_b['id']}/install")

        # Both POSTs accepted (different lock keys).
        assert resp_a.status_code == 202
        assert resp_b.status_code == 202

        _wait(server_a["id"])
        _wait(server_b["id"])
