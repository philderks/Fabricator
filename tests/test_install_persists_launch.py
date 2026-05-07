"""Successful install must persist launch into servers.json."""
from __future__ import annotations

from unittest.mock import patch

from backend.server.installer.base import InstallResult, InstallStatus, LaunchSpec


def _seed_server(tmp_servers_root):
    """Create one Fabric server record so install_server can be called."""
    from backend.server import storage
    return storage.create_server({
        "name": "Demo",
        "version": "1.21.4",
        "loader": "fabric",
        "port": 25565,
        "installPath": "demo",
        "memory": 2,
    })


def test_install_writes_launch_to_storage(client, tmp_servers_root):
    server = _seed_server(tmp_servers_root)
    server_id = server["id"]

    fake_result = InstallResult(
        success=True,
        status=InstallStatus.COMPLETED,
        message="ok",
        details={"mc_version": "1.21.4"},
        launch=LaunchSpec(
            type="jar",
            jar="server.jar",
            jvm_args=[],
            program_args=["nogui"],
        ),
    )

    # Skip Java enforcement — we only care about the persistence path.
    with patch.dict("os.environ", {"FABRICATOR_SKIP_JAVA_CHECK": "1"}), \
         patch(
             "backend.server.installer.fabric.FabricInstaller.install_with_config",
             return_value=fake_result,
         ):
        response = client.post(f"/api/servers/{server_id}/install")

    assert response.status_code == 200
    body = response.get_json()
    assert body["success"] is True

    from backend.server import storage
    persisted = storage.get_server(server_id)
    assert persisted["launch"] == {
        "type": "jar",
        "jar": "server.jar",
        "jvm_args": [],
        "program_args": ["nogui"],
    }


def test_install_failure_does_not_write_launch(client, tmp_servers_root):
    server = _seed_server(tmp_servers_root)
    server_id = server["id"]

    fake_result = InstallResult(
        success=False,
        status=InstallStatus.FAILED,
        message="boom",
        launch=None,
    )

    with patch.dict("os.environ", {"FABRICATOR_SKIP_JAVA_CHECK": "1"}), \
         patch(
             "backend.server.installer.fabric.FabricInstaller.install_with_config",
             return_value=fake_result,
         ):
        client.post(f"/api/servers/{server_id}/install")

    from backend.server import storage
    persisted = storage.get_server(server_id)
    assert "launch" not in persisted
