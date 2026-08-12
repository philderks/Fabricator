"""A modpack asked for at create time survives the browser leaving.

Issue #63: creating a server with a modpack was two jobs, and only the loader
half ran on the server. The browser polled the loader install to completion and
then fired the modpack install itself, so closing the create screen or
refreshing the page meant nobody ever fired it — the server came up bare. The
Close button even said "continues in background", which was true of the loader
and false of the pack.

These tests pin the fix: the modpack intent travels with ``POST /install`` and
is carried out by the same worker thread, with no request in flight.
"""
from __future__ import annotations

import importlib
import time
from unittest.mock import patch

import pytest

from backend.modrinth import pending
from backend.server.installer.base import InstallResult, InstallStatus, LaunchSpec


def _install_progress_module():
    """Resolve install_progress through sys.modules — see test_install_async_route."""
    return importlib.import_module("backend.server.install_progress")


def _seed(suffix: str = "1"):
    from backend.server import storage
    return storage.create_server({
        "name": f"PendingTest-{suffix}",
        "version": "1.21.1",
        "loader": "fabric",
        "port": 25600 + int(suffix),
        "installPath": f"pending-test-{suffix}",
        "memory": 2,
    })


def _wait(server_id: str, timeout: float = 5.0) -> dict:
    deadline = time.time() + timeout
    ip = _install_progress_module()
    while time.time() < deadline:
        entry = ip.get(server_id)
        if entry.get("phase") in ("done", "failed"):
            return entry
        time.sleep(0.01)
    raise AssertionError(f"timeout: {ip.get(server_id)!r}")


OK_RESULT = InstallResult(
    success=True, status=InstallStatus.COMPLETED, message="ok",
    launch=LaunchSpec(type="jar", jar="server.jar", program_args=["nogui"]),
)


# ---------------------------------------------------------------------------
# Intent normalisation — this gets persisted on the server record, so it has
# to reject junk rather than store it.
# ---------------------------------------------------------------------------

def test_project_intent_is_kept():
    intent = pending.normalize_intent({
        "source": "project", "project_id": "AABBCCDD",
        "loader": "neoforge", "mc_version": "1.21.1",
    })
    assert intent["source"] == "project"
    assert intent["project_id"] == "AABBCCDD"
    assert intent["loader"] == "neoforge"
    assert "requested_at" in intent


def test_upload_intent_is_kept():
    intent = pending.normalize_intent({"source": "upload", "upload_id": "abc123"})
    assert intent["source"] == "upload"
    assert intent["upload_id"] == "abc123"


@pytest.mark.parametrize("raw", [
    None, {}, "modpack", 42,
    {"source": "project"},                      # no project id
    {"source": "upload"},                       # no upload id
    {"source": "elsewhere", "project_id": "x"},  # unknown source
    {"project_id": "x"},                        # no source
])
def test_uninstallable_intents_are_dropped(raw):
    """"No modpack" and "junk modpack" must be indistinguishable to the caller."""
    assert pending.normalize_intent(raw) is None


def test_unknown_fields_are_not_persisted():
    """This lands in storage — arbitrary client JSON must not ride along."""
    intent = pending.normalize_intent({
        "source": "project", "project_id": "x", "evil": "payload",
    })
    assert "evil" not in intent


def test_only_real_sides_survive_in_overrides():
    intent = pending.normalize_intent({
        "source": "project", "project_id": "x",
        "mod_side_overrides": {"mods/a.jar": "client", "mods/b.jar": "nonsense"},
    })
    assert intent["mod_side_overrides"] == {"mods/a.jar": "client"}


# ---------------------------------------------------------------------------
# The worker carries the install out
# ---------------------------------------------------------------------------

def test_modpack_is_installed_by_the_worker_not_the_browser(client, tmp_servers_root):
    """The reproduction of #63: nothing but POST /install is ever requested."""
    from backend.server import storage

    server = _seed("1")
    server_id = server["id"]
    _install_progress_module().clear(server_id)

    installed = {}

    def fake_install_modpack(**kwargs):
        installed.update(kwargs)
        return {
            "name": "Cool Pack", "version": "1.0", "mc_version": "1.21.1",
            "project_id": "PACK123", "version_id": "v1", "loaders": ["fabric"],
            "files_installed": ["mods/a.jar"], "files_skipped": [],
            "uncertain_mod_files": [], "missing_files": [],
        }

    with patch.dict("os.environ", {"FABRICATOR_SKIP_JAVA_CHECK": "1"}), \
         patch("backend.server.installer.fabric.FabricInstaller.install_with_config",
               return_value=OK_RESULT), \
         patch("backend.modrinth.client.ModrinthClient.install_modpack",
               side_effect=fake_install_modpack):
        resp = client.post(f"/api/servers/{server_id}/install", json={
            "modpack": {
                "source": "project", "project_id": "PACK123",
                "loader": "fabric", "mc_version": "1.21.1",
            },
        })
        assert resp.status_code == 202
        final = _wait(server_id)

    assert installed["project_id"] == "PACK123"
    assert final["phase"] == "done"
    assert final.get("modpack_installed") is True
    assert "modpack_error" not in final

    record = storage.get_server(server_id)
    assert record["modpack"]["name"] == "Cool Pack"
    assert record["modpack"]["projectId"] == "PACK123"
    # The intent is consumed, not left behind to run twice.
    assert record.get("pendingModpack") is None


def test_install_without_a_modpack_is_untouched(client, tmp_servers_root):
    """A loader-only create must not gain a modpack step."""
    from backend.server import storage

    server = _seed("2")
    server_id = server["id"]
    _install_progress_module().clear(server_id)

    with patch.dict("os.environ", {"FABRICATOR_SKIP_JAVA_CHECK": "1"}), \
         patch("backend.server.installer.fabric.FabricInstaller.install_with_config",
               return_value=OK_RESULT), \
         patch("backend.modrinth.client.ModrinthClient.install_modpack") as never:
        resp = client.post(f"/api/servers/{server_id}/install")
        assert resp.status_code == 202
        final = _wait(server_id)

    never.assert_not_called()
    assert final["phase"] == "done"
    assert "modpack_installed" not in final
    assert storage.get_server(server_id).get("modpack") is None


def test_a_failing_modpack_still_leaves_a_usable_server(client, tmp_servers_root):
    """The loader is in and the server boots; only the pack is reported failed.

    Failing the whole create would strand a server that is perfectly fine, and
    the user cannot answer a prompt that arrives after they closed the screen.
    """
    from backend.server import storage

    server = _seed("3")
    server_id = server["id"]
    _install_progress_module().clear(server_id)

    with patch.dict("os.environ", {"FABRICATOR_SKIP_JAVA_CHECK": "1"}), \
         patch("backend.server.installer.fabric.FabricInstaller.install_with_config",
               return_value=OK_RESULT), \
         patch("backend.modrinth.client.ModrinthClient.install_modpack",
               side_effect=RuntimeError("modrinth exploded")):
        resp = client.post(f"/api/servers/{server_id}/install", json={
            "modpack": {"source": "project", "project_id": "PACK123"},
        })
        assert resp.status_code == 202
        final = _wait(server_id)

    assert final["phase"] == "done"
    assert "modrinth exploded" in final["modpack_error"]

    record = storage.get_server(server_id)
    assert record["status"] == "stopped", "server must remain usable"
    assert record.get("modpack") is None
    assert record.get("pendingModpack") is None


def test_a_failed_loader_install_does_not_run_the_modpack(client, tmp_servers_root):
    """No loader, nothing to install a pack onto."""
    server = _seed("4")
    server_id = server["id"]
    _install_progress_module().clear(server_id)

    failed = InstallResult(
        success=False, status=InstallStatus.FAILED, message="loader broke", launch=None,
    )

    with patch.dict("os.environ", {"FABRICATOR_SKIP_JAVA_CHECK": "1"}), \
         patch("backend.server.installer.fabric.FabricInstaller.install_with_config",
               return_value=failed), \
         patch("backend.modrinth.client.ModrinthClient.install_modpack") as never:
        resp = client.post(f"/api/servers/{server_id}/install", json={
            "modpack": {"source": "project", "project_id": "PACK123"},
        })
        assert resp.status_code == 202
        final = _wait(server_id)

    never.assert_not_called()
    assert final["phase"] == "failed"


def test_uncertain_mods_are_recorded_rather_than_prompted(client, tmp_servers_root):
    """Nobody is watching, so warnings are kept for the dashboard to show."""
    from backend.server import storage

    server = _seed("5")
    server_id = server["id"]
    _install_progress_module().clear(server_id)

    uncertain = [{"path": "mods/mystery.jar", "reason": "no side declared"}]

    with patch.dict("os.environ", {"FABRICATOR_SKIP_JAVA_CHECK": "1"}), \
         patch("backend.server.installer.fabric.FabricInstaller.install_with_config",
               return_value=OK_RESULT), \
         patch("backend.modrinth.client.ModrinthClient.install_modpack",
               return_value={
                   "name": "Pack", "loaders": [], "files_installed": [],
                   "files_skipped": [], "missing_files": [],
                   "uncertain_mod_files": uncertain,
               }):
        resp = client.post(f"/api/servers/{server_id}/install", json={
            "modpack": {"source": "project", "project_id": "PACK123"},
        })
        assert resp.status_code == 202
        final = _wait(server_id)

    assert final["modpack_uncertain"] == 1
    assert storage.get_server(server_id)["modpack"]["uncertainMods"] == uncertain


def test_an_expired_upload_is_reported_not_crashed(client, tmp_servers_root):
    """A staged .mrpack swept before the worker got to it fails cleanly."""
    server = _seed("6")
    server_id = server["id"]
    _install_progress_module().clear(server_id)

    with patch.dict("os.environ", {"FABRICATOR_SKIP_JAVA_CHECK": "1"}), \
         patch("backend.server.installer.fabric.FabricInstaller.install_with_config",
               return_value=OK_RESULT):
        resp = client.post(f"/api/servers/{server_id}/install", json={
            "modpack": {"source": "upload", "upload_id": "long-gone"},
        })
        assert resp.status_code == 202
        final = _wait(server_id)

    assert final["phase"] == "done"
    assert "no longer available" in final["modpack_error"]
