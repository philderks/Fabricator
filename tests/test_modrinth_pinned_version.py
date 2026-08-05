"""Installing a named mod version, and swapping an installed one (issue #56).

Install always took whatever resolved as newest, so pinning an older build for
compatibility meant dropping the jar into mods/ by hand — which then left the
panel reporting the wrong version, since a hand-dropped jar has no manifest
entry.

`version_id` names the version; `replaces` names the jar it supersedes. Both
come from the client, so both are validated here: a version must actually
belong to the project it is being installed under, and `replaces` must name a
plain file inside the mods folder.
"""
from __future__ import annotations

import importlib
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from backend.modrinth.client import ModrinthApiError


@pytest.fixture(autouse=True)
def _fresh_modules():
    """Re-bind against what sys.modules holds NOW — test_app_factory.py purges
    every `backend.*` module. Same idiom as test_playit_provision.py."""
    global ModrinthApiError
    ModrinthApiError = importlib.import_module("backend.modrinth.client").ModrinthApiError


def _make_server(app, tmp_servers_root, port, path):
    from backend.server import storage

    with app.app_context():
        server = storage.create_server({
            "name": path, "version": "1.21.4", "loader": "fabric",
            "port": port, "installPath": path,
        })
    mods = tmp_servers_root / "servers" / path / "mods"
    mods.mkdir(parents=True, exist_ok=True)
    return server["id"], mods


def _version(version_id="vPIN", project_id="AANobbMI", number="0.5.0", url="https://cdn/x.jar"):
    return {
        "id": version_id,
        "project_id": project_id,
        "version_number": number,
        "files": [{"url": url, "primary": True, "filename": "mod-0.5.0.jar",
                   "hashes": {"sha1": "abc"}}],
    }


# ---------------------------------------------------------------------------
# client.get_pinned_download
# ---------------------------------------------------------------------------

def _client():
    from backend.modrinth.client import ModrinthClient
    from backend.modrinth.ratelimit import RateLimiter
    return ModrinthClient(limiter=RateLimiter(capacity=1000, window_seconds=1.0))


def test_pinned_download_returns_that_versions_file():
    client = _client()
    with patch.object(client, "get_version", return_value=_version()):
        resolved = client.get_pinned_download("AANobbMI", "vPIN")
    assert resolved["version_id"] == "vPIN"
    assert resolved["version_number"] == "0.5.0"
    assert resolved["hashes"] == {"sha1": "abc"}


def test_pinned_download_accepts_a_slug():
    """`mod_id` is often a slug, so a straight string compare against the
    version's project_id would reject every legitimate install."""
    client = _client()
    with patch.object(client, "get_version", return_value=_version()), \
         patch.object(client, "get_project", return_value={"id": "AANobbMI", "slug": "sodium"}):
        resolved = client.get_pinned_download("sodium", "vPIN")
    assert resolved["version_id"] == "vPIN"


def test_pinned_download_rejects_a_version_from_another_project():
    """Without this, any version id could be installed under any project's
    name — and the manifest would record the wrong project entirely."""
    client = _client()
    with patch.object(client, "get_version", return_value=_version(project_id="OTHER")), \
         patch.object(client, "get_project", return_value={"id": "AANobbMI"}):
        with pytest.raises(ModrinthApiError) as excinfo:
            client.get_pinned_download("sodium", "vPIN")
    assert excinfo.value.status_code == 400
    assert "does not belong" in str(excinfo.value)


def test_pinned_download_returns_none_without_a_primary_file():
    client = _client()
    version = _version()
    version["files"] = []
    with patch.object(client, "get_version", return_value=version):
        assert client.get_pinned_download("AANobbMI", "vPIN") is None


# ---------------------------------------------------------------------------
# install route — version_id
# ---------------------------------------------------------------------------

def _install(client, sid, **body):
    payload = {"server_id": sid, "mc_version": "1.21.4", "loader": "fabric"}
    payload.update(body)
    return client.post("/api/modrinth/mod/sodium/install", json=payload)


def test_install_uses_the_named_version(client, app, tmp_servers_root):
    sid, mods = _make_server(app, tmp_servers_root, 25931, "pin-a")

    with patch("backend.modrinth.routes.modrinth_client") as mc:
        mc.get_pinned_download.return_value = {
            "url": "https://cdn/old.jar", "hashes": {},
            "version_id": "vOLD", "version_number": "0.4.0",
        }
        mc.download_mod.return_value = mods / "sodium-0.4.0.jar"
        mc.get_project.return_value = {"id": "AANobbMI", "slug": "sodium", "title": "Sodium"}
        resp = _install(client, sid, version_id="vOLD")

    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    assert body["versionNumber"] == "0.4.0"
    # The auto-resolver must not have run — that would defeat the pin.
    mc.get_project_download_url.assert_not_called()
    mc.get_pinned_download.assert_called_once_with("sodium", "vOLD")


def test_install_without_version_id_still_auto_resolves(client, app, tmp_servers_root):
    """Regression guard: the existing install path is untouched."""
    sid, mods = _make_server(app, tmp_servers_root, 25932, "pin-b")

    with patch("backend.modrinth.routes.modrinth_client") as mc:
        mc.get_project_download_url.return_value = {
            "url": "https://cdn/new.jar", "hashes": {},
            "version_id": "vNEW", "version_number": "0.6.0",
        }
        mc.download_mod.return_value = mods / "sodium-0.6.0.jar"
        mc.get_project.return_value = {"id": "AANobbMI"}
        resp = _install(client, sid)

    assert resp.status_code == 200
    mc.get_pinned_download.assert_not_called()


def test_pinned_install_is_recorded_as_pinned(client, app, tmp_servers_root):
    """The manifest distinguishes a deliberate pin from an auto-resolved
    install, so a future update-all can leave pins alone."""
    from backend.server import storage

    sid, mods = _make_server(app, tmp_servers_root, 25933, "pin-c")
    with patch("backend.modrinth.routes.modrinth_client") as mc:
        mc.get_pinned_download.return_value = {
            "url": "https://cdn/old.jar", "hashes": {},
            "version_id": "vOLD", "version_number": "0.4.0",
        }
        mc.download_mod.return_value = mods / "sodium-0.4.0.jar"
        mc.get_project.return_value = {"id": "AANobbMI", "title": "Sodium"}
        _install(client, sid, version_id="vOLD")

    with app.app_context():
        entry = storage.get_content_manifest(sid)["sodium-0.4.0.jar"]
    assert entry["pinned"] is True
    assert entry["versionId"] == "vOLD"
    assert entry["versionNumber"] == "0.4.0"


def test_auto_install_is_not_recorded_as_pinned(client, app, tmp_servers_root):
    from backend.server import storage

    sid, mods = _make_server(app, tmp_servers_root, 25934, "pin-d")
    with patch("backend.modrinth.routes.modrinth_client") as mc:
        mc.get_project_download_url.return_value = {
            "url": "https://cdn/new.jar", "hashes": {},
            "version_id": "vNEW", "version_number": "0.6.0",
        }
        mc.download_mod.return_value = mods / "sodium-0.6.0.jar"
        mc.get_project.return_value = {"id": "AANobbMI"}
        _install(client, sid)

    with app.app_context():
        assert storage.get_content_manifest(sid)["sodium-0.6.0.jar"]["pinned"] is False


def test_version_with_no_file_is_404(client, app, tmp_servers_root):
    sid, _ = _make_server(app, tmp_servers_root, 25935, "pin-e")
    with patch("backend.modrinth.routes.modrinth_client") as mc:
        mc.get_pinned_download.return_value = None
        resp = _install(client, sid, version_id="vEMPTY")
    assert resp.status_code == 404
    assert "no downloadable file" in resp.get_json()["error"]


def test_mismatched_version_is_rejected_by_the_route(client, app, tmp_servers_root):
    sid, _ = _make_server(app, tmp_servers_root, 25936, "pin-f")
    with patch("backend.modrinth.routes.modrinth_client") as mc:
        mc.get_pinned_download.side_effect = ModrinthApiError(
            "Version vX does not belong to sodium", status_code=400
        )
        resp = _install(client, sid, version_id="vX")
    assert resp.status_code == 400
    assert "does not belong" in resp.get_json()["error"]


# ---------------------------------------------------------------------------
# install route — replaces (the "change version" swap)
# ---------------------------------------------------------------------------

def test_replaces_removes_the_superseded_jar(client, app, tmp_servers_root):
    from backend.server import storage

    sid, mods = _make_server(app, tmp_servers_root, 25941, "swap-a")
    old = mods / "sodium-0.4.0.jar"
    old.write_bytes(b"old")
    with app.app_context():
        storage.record_content_install(sid, old.name, {"projectId": "AANobbMI"})

    with patch("backend.modrinth.routes.modrinth_client") as mc:
        mc.get_pinned_download.return_value = {
            "url": "https://cdn/new.jar", "hashes": {},
            "version_id": "vNEW", "version_number": "0.6.0",
        }
        new = mods / "sodium-0.6.0.jar"
        new.write_bytes(b"new")
        mc.download_mod.return_value = new
        mc.get_project.return_value = {"id": "AANobbMI"}
        resp = _install(client, sid, version_id="vNEW", replaces=old.name)

    assert resp.status_code == 200
    assert resp.get_json()["replaced"] == "sodium-0.4.0.jar"
    assert not old.exists(), "the superseded jar must be gone"
    assert new.exists()
    with app.app_context():
        assert old.name not in storage.get_content_manifest(sid)


def test_failed_download_leaves_the_old_jar_alone(client, app, tmp_servers_root):
    """The swap must never strand a server with no copy of the mod."""
    sid, mods = _make_server(app, tmp_servers_root, 25942, "swap-b")
    old = mods / "sodium-0.4.0.jar"
    old.write_bytes(b"old")

    with patch("backend.modrinth.routes.modrinth_client") as mc:
        mc.get_pinned_download.return_value = {
            "url": "https://cdn/new.jar", "hashes": {},
            "version_id": "vNEW", "version_number": "0.6.0",
        }
        mc.download_mod.side_effect = ModrinthApiError("network died", status_code=502)
        resp = _install(client, sid, version_id="vNEW", replaces=old.name)

    assert resp.status_code == 502
    assert old.exists(), "old jar must survive a failed replacement"


def test_replacing_with_the_same_filename_keeps_the_file(client, app, tmp_servers_root):
    """Reinstalling the version already on disk must not delete what was just
    written — same name means the download overwrote it in place."""
    sid, mods = _make_server(app, tmp_servers_root, 25943, "swap-c")
    jar = mods / "sodium-0.6.0.jar"
    jar.write_bytes(b"same")

    with patch("backend.modrinth.routes.modrinth_client") as mc:
        mc.get_pinned_download.return_value = {
            "url": "https://cdn/same.jar", "hashes": {},
            "version_id": "vSAME", "version_number": "0.6.0",
        }
        mc.download_mod.return_value = jar
        mc.get_project.return_value = {"id": "AANobbMI"}
        resp = _install(client, sid, version_id="vSAME", replaces=jar.name)

    assert resp.status_code == 200
    assert resp.get_json()["replaced"] is None
    assert jar.exists()


def test_missing_replaces_target_is_not_an_error(client, app, tmp_servers_root):
    """The user may have removed the old jar by hand between opening the picker
    and confirming; the install should still land."""
    sid, mods = _make_server(app, tmp_servers_root, 25944, "swap-d")

    with patch("backend.modrinth.routes.modrinth_client") as mc:
        mc.get_pinned_download.return_value = {
            "url": "https://cdn/new.jar", "hashes": {},
            "version_id": "vNEW", "version_number": "0.6.0",
        }
        mc.download_mod.return_value = mods / "sodium-0.6.0.jar"
        mc.get_project.return_value = {"id": "AANobbMI"}
        resp = _install(client, sid, version_id="vNEW", replaces="already-gone.jar")

    assert resp.status_code == 200
    assert resp.get_json()["replaced"] is None


@pytest.mark.parametrize("bad", [
    "../../server.jar",
    "/etc/passwd",
    "subdir/mod.jar",
    "..",
])
def test_replaces_rejects_paths_outside_the_mods_folder(client, app, tmp_servers_root, bad):
    """`replaces` names a file we are about to delete — it is untrusted input."""
    sid, _ = _make_server(app, tmp_servers_root, 25945, "swap-e")
    resp = _install(client, sid, version_id="vNEW", replaces=bad)
    assert resp.status_code == 400
    assert "replaces" in resp.get_json()["error"]


def test_replaces_rejects_non_jar_files(client, app, tmp_servers_root):
    """Nothing in the mods folder but jars should ever be swapped out — and
    server.properties lives one directory up, not here."""
    sid, _ = _make_server(app, tmp_servers_root, 25946, "swap-f")
    resp = _install(client, sid, version_id="vNEW", replaces="server.properties")
    assert resp.status_code == 400
    assert ".jar" in resp.get_json()["error"]


def test_replaces_is_validated_before_anything_downloads(client, app, tmp_servers_root):
    """A bad `replaces` must not leave a stray jar behind from a download that
    was going to be rejected anyway."""
    sid, _ = _make_server(app, tmp_servers_root, 25947, "swap-g")
    with patch("backend.modrinth.routes.modrinth_client") as mc:
        resp = _install(client, sid, version_id="vNEW", replaces="../evil.jar")
    assert resp.status_code == 400
    mc.download_mod.assert_not_called()
    mc.get_pinned_download.assert_not_called()
