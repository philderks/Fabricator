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
