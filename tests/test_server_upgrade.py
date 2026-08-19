"""Safety contract tests for the vanilla/Paper server upgrade service."""
from types import SimpleNamespace

import pytest

from backend.server.installer import InstallResult, InstallStatus, LaunchSpec


def _server(**overrides):
    server = {
        "id": "srv_upgrade",
        "loader": "vanilla",
        "version": "1.20.1",
        "status": "running",
    }
    server.update(overrides)
    return server


def test_upgrade_backs_up_stops_and_only_then_replaces_server_version(monkeypatch, tmp_path):
    from backend.server import upgrade

    server = _server()
    events = []
    updates = []

    class Registry:
        def resolve_install_path(self, record):
            assert record == server
            return tmp_path

        def stop_server(self, server_id):
            events.append(("stop", server_id))
            return {"status": "stopped"}

    result = InstallResult(
        success=True,
        status=InstallStatus.COMPLETED,
        message="installed",
        launch=LaunchSpec(type="jar", jar="server.jar", program_args=["nogui"]),
    )

    class Installer:
        def install(self, mc_version, progress_callback=None):
            events.append(("install", mc_version))
            return result

    monkeypatch.setattr(upgrade.server_storage, "get_server", lambda _id: server)
    monkeypatch.setattr(upgrade, "get_server_process_registry", lambda: Registry())
    monkeypatch.setattr(
        upgrade.backup_service,
        "run_adhoc_backup",
        lambda server_id, **kwargs: events.append(("backup", server_id)) or {"id": "snap_1"},
    )
    monkeypatch.setattr(upgrade, "get_installer_for", lambda loader, path: Installer())
    monkeypatch.setattr(
        upgrade.server_storage,
        "update_server",
        lambda server_id, patch: updates.append((server_id, patch)) or {**server, **patch},
    )

    upgraded = upgrade.upgrade_server("srv_upgrade", "1.21")

    assert events == [
        ("backup", "srv_upgrade"),
        ("stop", "srv_upgrade"),
        ("install", "1.21"),
    ]
    assert upgraded["from_version"] == "1.20.1"
    assert upgraded["to_version"] == "1.21"
    assert updates == [
        (
            "srv_upgrade",
            {
                "version": "1.21",
                "launch": result.launch.to_dict(),
                "status": "stopped",
            },
        )
    ]


def test_upgrade_restores_original_jar_when_install_fails(monkeypatch, tmp_path):
    from backend.server import upgrade

    server = _server(status="stopped")
    jar_path = tmp_path / "server.jar"
    jar_path.write_bytes(b"known-good-old-server")

    class Registry:
        def resolve_install_path(self, record):
            return tmp_path

        def stop_server(self, server_id):
            return {"status": "stopped"}

    class FailingInstaller:
        def install(self, mc_version, progress_callback=None):
            # Mirrors a failed verified download, which may remove server.jar.
            jar_path.unlink()
            return InstallResult(
                success=False,
                status=InstallStatus.FAILED,
                message="download failed",
            )

    monkeypatch.setattr(upgrade.server_storage, "get_server", lambda _id: server)
    monkeypatch.setattr(upgrade, "get_server_process_registry", lambda: Registry())
    monkeypatch.setattr(
        upgrade.backup_service, "run_adhoc_backup", lambda *_args, **_kwargs: {"id": "snap_1"}
    )
    monkeypatch.setattr(upgrade, "get_installer_for", lambda *_args: FailingInstaller())

    with pytest.raises(upgrade.UpgradeError, match="download failed"):
        upgrade.upgrade_server("srv_upgrade", "1.21")

    assert jar_path.read_bytes() == b"known-good-old-server"


@pytest.mark.parametrize(
    ("loader", "target", "message"),
    [
        ("fabric", "1.21", "only supports vanilla and Paper"),
        ("vanilla", "1.20.1", "must be newer"),
        ("paper", "1.20", "must be newer"),
    ],
)
def test_upgrade_rejects_unsupported_loaders_and_downgrades(monkeypatch, loader, target, message):
    from backend.server import upgrade

    monkeypatch.setattr(upgrade.server_storage, "get_server", lambda _id: _server(loader=loader))

    with pytest.raises(upgrade.UpgradeError, match=message):
        upgrade.upgrade_server("srv_upgrade", target)


def test_upgrade_route_starts_a_tracked_upgrade_job(client, tmp_servers_root, monkeypatch):
    import threading
    import time

    from backend.server import storage
    from backend.server import upgrade as upgrade_service

    server = storage.create_server({
        "name": "Upgrade me",
        "version": "1.20.1",
        "loader": "vanilla",
        "port": 25565,
        "installPath": "upgrade-me",
    })
    called = []
    complete = threading.Event()

    def fake_upgrade(server_id, target_version, *, progress_callback):
        called.append((server_id, target_version))
        progress_callback("downloading_server_jar", {"bytes_done": 3, "bytes_total": 10})
        complete.set()
        return {"snapshot_id": "snap_upgrade"}

    monkeypatch.setattr(upgrade_service, "upgrade_server", fake_upgrade)

    response = client.post(f"/api/servers/{server['id']}/upgrade", json={"version": "1.21"})

    assert response.status_code == 202
    assert complete.wait(timeout=2)
    # The worker updates shared install-progress so the existing polling UI can
    # represent a long-running upgrade without a second job protocol.
    for _ in range(20):
        progress = client.get(f"/api/servers/{server['id']}/install/progress").get_json()
        if progress.get("phase") == "done":
            break
        time.sleep(0.01)
    assert called == [(server["id"], "1.21")]
    assert progress["phase"] == "done"
    assert progress["kind"] == "upgrade"
    assert progress["snapshot_id"] == "snap_upgrade"
