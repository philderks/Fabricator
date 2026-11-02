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


@pytest.mark.parametrize(
    ("current", "target"),
    [
        # Year-based releases upgrade among themselves (issue #75).
        ("26.2", "26.3"),
        ("26.2", "26.2.1"),
        ("26.2.1", "26.3"),
        # ...and the 1.x era still upgrades into the year-based one, since
        # every 26.x release postdates every 1.x release.
        ("1.21.4", "26.3"),
        ("1.20.1", "1.21"),
    ],
)
def test_upgrade_accepts_both_minecraft_naming_schemes(current, target):
    from backend.server import upgrade

    server = _server(version=current)

    assert upgrade.validate_upgrade(server, target) == target


@pytest.mark.parametrize(
    ("current", "target"),
    [
        # A year-based release is never a downgrade target for a 1.x server's
        # successor, and the reverse direction must stay refused.
        ("26.3", "1.21.4"),
        ("26.3", "26.2"),
        ("26.2.1", "26.2"),
    ],
)
def test_upgrade_rejects_downgrades_across_naming_schemes(current, target):
    from backend.server import upgrade

    with pytest.raises(upgrade.UpgradeError, match="must be newer"):
        upgrade.validate_upgrade(_server(version=current), target)


@pytest.mark.parametrize(
    "target",
    ["26w14a", "26.3-rc1", "26.2-snapshot-6", "1.21-pre1", "b1.7.3", "", "latest"],
)
def test_upgrade_still_rejects_non_release_targets(target):
    from backend.server import upgrade

    with pytest.raises(upgrade.UpgradeError, match="numbered Minecraft releases"):
        upgrade.validate_upgrade(_server(version="26.2"), target)


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


# ---------------------------------------------------------------------------
# Loader-build swap (#104)
# ---------------------------------------------------------------------------

class _LoaderInstaller:
    requires_java_for_install = True

    def __init__(self, events, result=None, builds=("21.1.169", "21.1.200")):
        self.events, self.result, self.builds = events, result, builds

    def get_available_versions(self, mc_version=None):
        return [{"version": b} for b in self.builds]

    def set_java_exec(self, path):
        self.events.append(("java", path))

    def install(self, mc_version, loader_version=None, progress_callback=None):
        self.events.append(("install", mc_version, loader_version))
        return self.result

    def install_with_config(self, *args, **kwargs):  # pragma: no cover - must not run
        raise AssertionError("install_with_config would overwrite server.properties")


def test_loader_upgrade_backs_up_stops_installs_build_and_records_it(monkeypatch, tmp_path):
    from backend.server import upgrade

    server = _server(loader="neoforge", version="1.21.1", loaderVersion="21.1.169")
    events, updates = [], []
    result = InstallResult(
        success=True, status=InstallStatus.COMPLETED, message="installed",
        launch=LaunchSpec(type="jar", jar="server.jar", program_args=["nogui"]),
    )
    installer = _LoaderInstaller(events, result)

    class Registry:
        def resolve_install_path(self, record):
            return tmp_path

        def get_java_runtime(self, record):
            return {"java_exec": "/jdk/bin/java", "java_missing": False}

        def stop_server(self, server_id):
            events.append(("stop", server_id))

    monkeypatch.setattr(upgrade.server_storage, "get_server", lambda _id: server)
    monkeypatch.setattr(upgrade, "get_server_process_registry", lambda: Registry())
    monkeypatch.setattr(
        upgrade.backup_service, "run_adhoc_backup",
        lambda server_id, **kwargs: events.append(("backup", server_id)) or {"id": "snap_1"},
    )
    monkeypatch.setattr(upgrade, "get_installer_for", lambda loader, path: installer)
    monkeypatch.setattr(
        upgrade.server_storage, "update_server",
        lambda server_id, patch: updates.append(patch) or {**server, **patch},
    )

    done = upgrade.upgrade_loader("srv_upgrade", "21.1.200")

    assert events == [
        ("java", "/jdk/bin/java"),
        ("backup", "srv_upgrade"),
        ("stop", "srv_upgrade"),
        ("install", "1.21.1", "21.1.200"),
    ]
    assert updates == [{
        "loaderVersion": "21.1.200", "status": "stopped", "launch": result.launch.to_dict(),
    }]
    assert done["from_loader_version"] == "21.1.169"
    assert done["to_loader_version"] == "21.1.200"


@pytest.mark.parametrize(
    "loader,build,message",
    [
        ("vanilla", "21.1.200", "only supported"),
        ("neoforge", "", "No loader version"),
        ("neoforge", "21.1.999", "not available"),
    ],
)
def test_loader_upgrade_rejects_unsupported_loaders_and_unknown_builds(monkeypatch, loader, build, message):
    from backend.server import upgrade

    monkeypatch.setattr(upgrade, "get_installer_for", lambda _l, _p: _LoaderInstaller([]))
    with pytest.raises(upgrade.UpgradeError, match=message):
        upgrade.validate_loader_upgrade(_server(loader=loader, version="1.21.1"), build)


def test_upgrade_route_dispatches_loader_version_to_loader_upgrade(client, tmp_servers_root, monkeypatch):
    import threading

    from backend.server import storage
    from backend.server import upgrade as upgrade_service

    server = storage.create_server({
        "name": "Pack", "version": "1.21.1", "loader": "neoforge",
        "port": 25566, "installPath": "pack-loader",
    })
    called = []
    complete = threading.Event()

    def fake_upgrade_loader(server_id, build, *, progress_callback):
        called.append((server_id, build))
        complete.set()
        return {"snapshot_id": "snap_loader"}

    monkeypatch.setattr(upgrade_service, "validate_loader_upgrade", lambda _s, build: build)
    monkeypatch.setattr(upgrade_service, "upgrade_loader", fake_upgrade_loader)

    response = client.post(
        f"/api/servers/{server['id']}/upgrade", json={"loader_version": "21.1.200"},
    )

    assert response.status_code == 202
    assert response.get_json()["kind"] == "loader_upgrade"
    assert complete.wait(timeout=2)
    assert called == [(server["id"], "21.1.200")]
