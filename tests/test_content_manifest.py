"""Install manifest: filename -> Modrinth project identity.

Project identity cannot be recovered from a jar filename after the fact —
plugin authors routinely ship a jar named nothing like the project slug
(`simple-voice-chat` -> `voicechat-bukkit-2.6.20.jar`). These tests pin the
record/read/forget cycle the UI relies on to mark a plugin "Installed".
"""
from __future__ import annotations

from unittest.mock import patch


_PORT = iter(range(25700, 25800))


def _create_server(client, loader="paper"):
    resp = client.post("/api/servers", json={
        "name": "pl",
        "version": "1.21.4",
        "loader": loader,
        "port": next(_PORT),
        "installPath": "pl",
    })
    assert resp.status_code in (200, 201), resp.get_json()
    return resp.get_json()["id"]


# ── storage layer ──────────────────────────────────────────────────────

def test_record_read_and_forget_roundtrip(app, tmp_servers_root):
    from backend.server import storage

    with app.app_context():
        server = storage.create_server({
            "name": "s", "version": "1.21.4", "loader": "paper",
            "port": next(_PORT), "installPath": "s",
        })
        sid = server["id"]

        assert storage.get_content_manifest(sid) == {}

        storage.record_content_install(sid, "voicechat-bukkit-2.6.20.jar", {
            "projectId": "9eGKb6K1", "slug": "simple-voice-chat",
        })
        manifest = storage.get_content_manifest(sid)
        assert manifest["voicechat-bukkit-2.6.20.jar"]["slug"] == "simple-voice-chat"

        storage.forget_content(sid, ["voicechat-bukkit-2.6.20.jar"])
        assert storage.get_content_manifest(sid) == {}


def test_forget_ignores_unknown_filenames(app, tmp_servers_root):
    """Hand-dropped jars have no entry; forgetting them must not raise."""
    from backend.server import storage

    with app.app_context():
        sid = storage.create_server({
            "name": "s", "version": "1.21.4", "loader": "paper",
            "port": next(_PORT), "installPath": "s",
        })["id"]
        storage.record_content_install(sid, "kept.jar", {"projectId": "AAA"})
        storage.forget_content(sid, ["never-recorded.jar"])
        assert "kept.jar" in storage.get_content_manifest(sid)


def test_record_preserves_sibling_entries(app, tmp_servers_root):
    """Two installs into one server must not drop each other's entry."""
    from backend.server import storage

    with app.app_context():
        sid = storage.create_server({
            "name": "s", "version": "1.21.4", "loader": "paper",
            "port": next(_PORT), "installPath": "s",
        })["id"]
        storage.record_content_install(sid, "a.jar", {"projectId": "AAA"})
        storage.record_content_install(sid, "b.jar", {"projectId": "BBB"})
        manifest = storage.get_content_manifest(sid)
        assert set(manifest) == {"a.jar", "b.jar"}


def test_manifest_of_unknown_server_is_empty(app, tmp_servers_root):
    from backend.server import storage
    with app.app_context():
        assert storage.get_content_manifest("srv_nope") == {}


def test_clear_wipes_manifest(app, tmp_servers_root):
    from backend.server import storage

    with app.app_context():
        sid = storage.create_server({
            "name": "s", "version": "1.21.4", "loader": "fabric",
            "port": next(_PORT), "installPath": "s",
        })["id"]
        storage.record_content_install(sid, "a.jar", {"projectId": "AAA"})
        storage.clear_content_manifest(sid)
        assert storage.get_content_manifest(sid) == {}


# ── install route records ──────────────────────────────────────────────

def test_install_records_project_identity(client, tmp_servers_root):
    sid = _create_server(client)

    resolved = {
        "url": "https://cdn.modrinth.com/x/voicechat-bukkit-2.6.20.jar",
        "hashes": {},
        "version_id": "VER123",
        "version_number": "2.6.20",
    }
    project = {
        "id": "9eGKb6K1",
        "slug": "simple-voice-chat",
        "title": "Simple Voice Chat",
        "icon_url": "https://cdn.modrinth.com/icon.png",
    }

    with patch("backend.modrinth.routes.modrinth_client.get_project_download_url",
               return_value=resolved), \
         patch("backend.modrinth.routes.modrinth_client.get_project",
               return_value=project), \
         patch("backend.modrinth.routes.modrinth_client.download_mod") as mock_dl:
        from pathlib import Path
        mock_dl.return_value = Path("/tmp/voicechat-bukkit-2.6.20.jar")
        resp = client.post("/api/modrinth/mod/9eGKb6K1/install", json={
            "server_id": sid, "mc_version": "1.21.4", "loader": "paper",
        })

    assert resp.status_code == 200, resp.get_json()

    from backend.server import storage
    entry = storage.get_content_manifest(sid)["voicechat-bukkit-2.6.20.jar"]
    assert entry["projectId"] == "9eGKb6K1"
    assert entry["slug"] == "simple-voice-chat"
    assert entry["title"] == "Simple Voice Chat"
    assert entry["iconUrl"] == "https://cdn.modrinth.com/icon.png"
    assert entry["versionNumber"] == "2.6.20"


def test_install_survives_project_metadata_failure(client, tmp_servers_root):
    """The jar is on disk and usable — a metadata fetch failure must not 500.

    The entry is still recorded with the id we already know, so the badge works
    even though the title/icon are missing.
    """
    from backend.modrinth.client import ModrinthApiError
    sid = _create_server(client)

    with patch("backend.modrinth.routes.modrinth_client.get_project_download_url",
               return_value={"url": "https://x/p.jar", "hashes": {},
                             "version_id": "V", "version_number": "1.0"}), \
         patch("backend.modrinth.routes.modrinth_client.get_project",
               side_effect=ModrinthApiError("boom", status_code=503)), \
         patch("backend.modrinth.routes.modrinth_client.download_mod") as mock_dl:
        from pathlib import Path
        mock_dl.return_value = Path("/tmp/p.jar")
        resp = client.post("/api/modrinth/mod/ABC/install", json={
            "server_id": sid, "mc_version": "1.21.4", "loader": "paper",
        })

    assert resp.status_code == 200
    from backend.server import storage
    assert storage.get_content_manifest(sid)["p.jar"]["projectId"] == "ABC"


# ── list route merges, delete route forgets ────────────────────────────

def test_list_mods_attaches_manifest_entry(client, tmp_servers_root):
    from backend.server import storage
    from backend.server.registry import get_server_process_registry

    sid = _create_server(client)
    server = storage.get_server(sid)
    plugins = get_server_process_registry().resolve_content_path(server)
    (plugins / "voicechat-bukkit-2.6.20.jar").write_bytes(b"jar")
    (plugins / "handdropped.jar").write_bytes(b"jar")

    storage.record_content_install(sid, "voicechat-bukkit-2.6.20.jar", {
        "projectId": "9eGKb6K1", "slug": "simple-voice-chat",
        "title": "Simple Voice Chat",
    })

    resp = client.get(f"/api/servers/{sid}/mods")
    assert resp.status_code == 200
    by_name = {e["name"]: e for e in resp.get_json()}

    assert by_name["voicechat-bukkit-2.6.20.jar"]["modrinth"]["slug"] == "simple-voice-chat"
    # No entry for a jar nobody recorded — the client falls back to guessing.
    assert "modrinth" not in by_name["handdropped.jar"]


def test_delete_mod_forgets_manifest_entry(client, tmp_servers_root):
    from backend.server import storage
    from backend.server.registry import get_server_process_registry

    sid = _create_server(client)
    server = storage.get_server(sid)
    plugins = get_server_process_registry().resolve_content_path(server)
    (plugins / "p.jar").write_bytes(b"jar")
    storage.record_content_install(sid, "p.jar", {"projectId": "ABC"})

    resp = client.delete(f"/api/servers/{sid}/mods/p.jar")
    assert resp.status_code == 200
    assert storage.get_content_manifest(sid) == {}


def test_bulk_delete_forgets_manifest_entries(client, tmp_servers_root):
    from backend.server import storage
    from backend.server.registry import get_server_process_registry

    sid = _create_server(client)
    server = storage.get_server(sid)
    plugins = get_server_process_registry().resolve_content_path(server)
    for name in ("a.jar", "b.jar", "c.jar"):
        (plugins / name).write_bytes(b"jar")
        storage.record_content_install(sid, name, {"projectId": name})

    resp = client.delete(f"/api/servers/{sid}/mods", json={"filenames": ["a.jar", "b.jar"]})
    assert resp.status_code == 200
    assert set(storage.get_content_manifest(sid)) == {"c.jar"}
