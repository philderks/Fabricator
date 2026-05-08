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
        "args_file": None,
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


def test_install_then_command_built_from_persisted_launch(client, tmp_servers_root, monkeypatch):
    """End-to-end: install writes launch → registry builds command from it.

    Guards the central Phase-0 invariant — that the persisted LaunchSpec is
    actually what drives the JVM command on next start, not a hardcoded
    constant elsewhere.
    """
    from unittest.mock import patch
    from backend.server.installer.base import InstallResult, InstallStatus, LaunchSpec

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
            jvm_args=["-Dlog4j2.formatMsgNoLookups=true"],
            program_args=["nogui"],
        ),
    )

    with patch.dict("os.environ", {"FABRICATOR_SKIP_JAVA_CHECK": "1"}), \
         patch(
             "backend.server.installer.fabric.FabricInstaller.install_with_config",
             return_value=fake_result,
         ):
        resp = client.post(f"/api/servers/{server_id}/install")
    assert resp.status_code == 200

    from backend.server import storage
    from backend.server.registry import get_server_process_registry
    persisted = storage.get_server(server_id)
    reg = get_server_process_registry()
    monkeypatch.setattr(reg, "_resolve_java_exec", lambda s: "/opt/java/bin/java")

    cmd = reg._build_command(persisted)
    assert cmd == [
        "/opt/java/bin/java",
        "-Xms2G",  # memory=2 was set in _seed_server
        "-Xmx2G",
        "-Dlog4j2.formatMsgNoLookups=true",
        "-jar",
        "server.jar",
        "nogui",
    ]


def test_neoforge_install_then_command_built_from_persisted_args_file(client, tmp_servers_root, monkeypatch):
    """End-to-end: NeoForge install writes args_file launch → registry builds @argfile command.

    Mirrors test_install_then_command_built_from_persisted_launch (jar-type)
    for the args_file-type LaunchSpec. Locks the Phase-2 invariant that
    NeoForge's persisted launch drives _build_command via the args_file
    branch.
    """
    from unittest.mock import patch
    from backend.server.installer.base import InstallResult, InstallStatus, LaunchSpec
    from backend.server import storage

    server = storage.create_server({
        "name": "Demo-NF",
        "version": "1.21.1",
        "loader": "neoforge",
        "port": 25567,
        "installPath": "demo-nf",
        "memory": 6,
    })
    server_id = server["id"]

    fake_result = InstallResult(
        success=True,
        status=InstallStatus.COMPLETED,
        message="ok",
        details={"mc_version": "1.21.1", "loader_version": "21.1.228"},
        launch=LaunchSpec(
            type="args_file",
            args_file="libraries/net/neoforged/neoforge/21.1.228/unix_args.txt",
            jvm_args=[],
            program_args=["nogui"],
        ),
    )

    fake_runtime = {
        "available": True,
        "java_exec": "/opt/java/bin/java",
        "major_version": 21,
        "version_output": "openjdk version \"21\"",
        "message": "ok",
        "java_missing": False,
    }

    with patch.dict("os.environ", {"FABRICATOR_SKIP_JAVA_CHECK": "1"}), \
         patch(
             "backend.server.registry.ServerProcessRegistry.get_java_runtime",
             return_value=fake_runtime,
         ), \
         patch(
             "backend.server.installer.neoforge.NeoForgeInstaller.install_with_config",
             return_value=fake_result,
         ):
        resp = client.post(f"/api/servers/{server_id}/install")
    assert resp.status_code == 200

    from backend.server.registry import get_server_process_registry
    persisted = storage.get_server(server_id)
    assert persisted["launch"]["type"] == "args_file"
    assert persisted["launch"]["args_file"] == (
        "libraries/net/neoforged/neoforge/21.1.228/unix_args.txt"
    )

    reg = get_server_process_registry()
    monkeypatch.setattr(reg, "_resolve_java_exec", lambda s: "/opt/java/bin/java")

    cmd = reg._build_command(persisted)
    assert cmd == [
        "/opt/java/bin/java",
        "-Xms6G",
        "-Xmx6G",
        "@libraries/net/neoforged/neoforge/21.1.228/unix_args.txt",
        "nogui",
    ]
