"""Route guard: install_server must keep returning the java_missing payload
for installers that require Java (existing or via the new requires_java_for_install
property). Phase 2 adds the second branch; this file holds both the regression
test for Fabric (existing branch) and the NeoForge end-to-end test (Task 7)."""
from __future__ import annotations

from unittest.mock import patch


def _seed_server(tmp_servers_root, loader: str, mc_version: str = "1.21.4"):
    from backend.server import storage
    return storage.create_server({
        "name": f"Demo-{loader}",
        "version": mc_version,
        "loader": loader,
        "port": 25566,
        "installPath": f"demo-{loader}",
        "memory": 4,
    })


def test_install_for_fabric_without_java_unchanged_behavior(client, tmp_servers_root):
    """Existing MC-compat branch still fires for Fabric+1.21 with no Java."""
    server = _seed_server(tmp_servers_root, loader="fabric")
    server_id = server["id"]

    fake_runtime = {
        "available": False,
        "java_exec": "java",
        "major_version": None,
        "version_output": "",
        "message": "missing",
        "java_missing": True,
    }

    with patch(
        "backend.server.registry.ServerProcessRegistry.get_java_runtime",
        return_value=fake_runtime,
    ):
        response = client.post(f"/api/servers/{server_id}/install")

    assert response.status_code == 400
    body = response.get_json()
    assert body["java_missing"] is True


def test_install_for_neoforge_without_java_returns_java_missing(client, tmp_servers_root):
    """End-to-end: NeoForge install on a host with no Java fires the new guard.

    We mock MC compat to non-enforceable so the existing branch does NOT fire
    — proving that the new requires_java_for_install branch is what catches it.
    """
    from backend.server import storage
    server = _seed_server(tmp_servers_root, loader="neoforge", mc_version="1.21.4")
    server_id = server["id"]

    fake_runtime = {
        "available": False,
        "java_exec": "java",
        "major_version": None,
        "version_output": "",
        "message": "Java executable 'java' is not installed or not found.",
        "java_missing": True,
    }

    class FakeCompat:
        required_java = None
        enforceable = False

        def to_dict(self):
            return {
                "mc_version": "1.21.4",
                "required_java": None,
                "enforceable": False,
                "confidence": "low",
                "reason": "test",
                "warning": None,
            }

    with patch(
        "backend.server.registry.ServerProcessRegistry.get_java_runtime",
        return_value=fake_runtime,
    ), patch(
        "backend.server.routes.resolve_required_java",
        return_value=FakeCompat(),
    ):
        response = client.post(f"/api/servers/{server_id}/install")

    assert response.status_code == 400
    body = response.get_json()
    assert body["success"] is False
    assert body["java_missing"] is True
    assert body["java_too_old"] is False
    persisted = storage.get_server(server_id)
    assert persisted["status"] == "stopped"


def test_java_guard_failure_clears_install_progress_entry(client, tmp_servers_root):
    """A Java-guard 400 must NOT leave a stale 'starting' progress entry.

    Phase 3c writes a 'starting' busy-marker BEFORE the Java guards to
    close the race window where two concurrent POSTs could both pass
    validation. That marker MUST be cleared on every 400 path or the
    user's retry (after fixing Java) gets a spurious 409 from the
    is_active check at the top of the route.
    """
    from backend.server import install_progress
    server = _seed_server(tmp_servers_root, loader="fabric")
    server_id = server["id"]
    install_progress.clear(server_id)  # paranoid baseline

    fake_runtime = {
        "available": False,
        "java_exec": "java",
        "major_version": None,
        "version_output": "",
        "message": "missing",
        "java_missing": True,
    }

    with patch(
        "backend.server.registry.ServerProcessRegistry.get_java_runtime",
        return_value=fake_runtime,
    ):
        response = client.post(f"/api/servers/{server_id}/install")

    assert response.status_code == 400
    # Progress entry cleared — is_active False, retry not blocked.
    assert install_progress.get(server_id) == {}
    assert install_progress.is_active(server_id) is False


def test_retry_after_java_guard_failure_is_not_blocked_by_409(client, tmp_servers_root):
    """User: install fails on Java guard → installs Java → retry must work.

    Pre-fix, the 'starting' marker would still be present, and the retry
    POST would short-circuit on is_active and return 409 even though no
    install thread was actually running.
    """
    from backend.server.installer.base import InstallResult, InstallStatus, LaunchSpec

    server = _seed_server(tmp_servers_root, loader="fabric")
    server_id = server["id"]

    # Round 1: Java missing → 400.
    fake_runtime_missing = {
        "available": False, "java_exec": "java", "major_version": None,
        "version_output": "", "message": "missing", "java_missing": True,
    }
    with patch(
        "backend.server.registry.ServerProcessRegistry.get_java_runtime",
        return_value=fake_runtime_missing,
    ):
        resp_first = client.post(f"/api/servers/{server_id}/install")
    assert resp_first.status_code == 400

    # Round 2 (user fixed Java): retry must succeed (202), NOT 409.
    fake_result = InstallResult(
        success=True, status=InstallStatus.COMPLETED, message="ok",
        launch=LaunchSpec(type="jar", jar="server.jar", program_args=["nogui"]),
    )
    with patch.dict("os.environ", {"FABRICATOR_SKIP_JAVA_CHECK": "1"}), \
         patch(
             "backend.server.registry.ServerProcessRegistry.get_java_runtime",
             return_value={
                 "available": True, "java_exec": "java", "major_version": 21,
                 "version_output": "", "message": "ok", "java_missing": False,
             },
         ), patch(
             "backend.server.installer.fabric.FabricInstaller.install_with_config",
             return_value=fake_result,
         ):
        resp_second = client.post(f"/api/servers/{server_id}/install")

    assert resp_second.status_code == 202, (
        f"retry was incorrectly blocked: {resp_second.status_code} "
        f"{resp_second.get_data(as_text=True)}"
    )

    # Wait for the second install thread to complete so the test cleanup
    # doesn't race with the worker.
    import time
    deadline = time.time() + 5.0
    from backend.server import install_progress
    while time.time() < deadline:
        if install_progress.get(server_id).get("phase") in ("done", "failed"):
            break
        time.sleep(0.01)
