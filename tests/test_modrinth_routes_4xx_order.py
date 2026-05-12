"""B14a 4xx-Order Regression-Pin.

Decorator stack ``@require_server`` (with ``source='url'`` or
``'body'``) sits above ``@with_server_lock`` (per ``utils/routes.py``
stacking convention), which means the 4xx fan-out is:

1. ``@require_server`` runs first:
   - source='body': missing ``server_id`` in JSON → ``400``
   - both sources:  server not in storage    → ``404``
2. ``@with_server_lock`` runs next:
   - lock held by another op                → ``409``
3. Handler body runs last with its own 400 / 404 ordering.

These tests pin the **current** order against accidental drift in
future refactors (e.g. swapping decorator order, or moving a
validation up from the handler body into a decorator).
"""
from __future__ import annotations

from unittest.mock import patch


# ---------------------------------------------------------------------------
# POST /api/modrinth/mod/<mod_id>/install — decorators in body mode
# ---------------------------------------------------------------------------


def test_install_mod_missing_server_id_returns_400_before_404(client, tmp_servers_root):
    """No ``server_id`` in body → 400 from @require_server(source='body')."""
    resp = client.post(
        "/api/modrinth/mod/SOMEMOD/install",
        json={"mc_version": "1.20.1", "loader": "fabric"},
    )
    assert resp.status_code == 400
    body = resp.get_json()
    assert "server_id" in body["error"].lower()


def test_install_mod_unknown_server_returns_404(client, tmp_servers_root):
    """``server_id`` present but unknown → 404 from @require_server."""
    resp = client.post(
        "/api/modrinth/mod/SOMEMOD/install",
        json={"server_id": "srv_nonexistent", "mc_version": "1.20.1"},
    )
    assert resp.status_code == 404
    assert "not found" in resp.get_json()["error"].lower()


def test_install_mod_missing_mc_version_returns_400_after_decorators(
    client, tmp_servers_root
):
    """Server exists, no lock contention → handler-body 400 for missing mc_version."""
    from backend.server import storage
    server = storage.create_server({
        "name": "Srv",
        "version": "1.20.1",
        "loader": "fabric",
        "port": 25590,
        "installPath": "srv-mc",
        "memory": 4,
    })
    resp = client.post(
        "/api/modrinth/mod/SOMEMOD/install",
        json={"server_id": server["id"]},  # no mc_version
    )
    assert resp.status_code == 400
    assert "mc_version" in resp.get_json()["error"].lower()


def test_install_mod_mods_folder_override_returns_400(client, tmp_servers_root):
    """``mods_folder`` override is rejected with 400 after mc_version check."""
    from backend.server import storage
    server = storage.create_server({
        "name": "Srv",
        "version": "1.20.1",
        "loader": "fabric",
        "port": 25591,
        "installPath": "srv-mf",
        "memory": 4,
    })
    resp = client.post(
        "/api/modrinth/mod/SOMEMOD/install",
        json={
            "server_id": server["id"],
            "mc_version": "1.20.1",
            "mods_folder": "/etc/passwd",
        },
    )
    assert resp.status_code == 400
    assert "mods_folder" in resp.get_json()["error"].lower()


# ---------------------------------------------------------------------------
# PUT /api/servers/<server_id>/settings — decorators in URL mode
# ---------------------------------------------------------------------------


def test_update_server_settings_unknown_server_returns_404(client, tmp_servers_root):
    resp = client.put(
        "/api/servers/srv_nope/settings",
        json={"name": "Whatever"},
    )
    assert resp.status_code == 404


def test_update_server_settings_empty_body_returns_400(client, tmp_servers_root):
    from backend.server import storage
    server = storage.create_server({
        "name": "S", "version": "1.20.1", "loader": "fabric",
        "port": 25592, "installPath": "srv-set", "memory": 4,
    })
    resp = client.put(
        f"/api/servers/{server['id']}/settings",
        json={},  # empty body → handler's "Request body is required" 400
    )
    assert resp.status_code == 400
    assert "body" in resp.get_json()["error"].lower()


def test_update_server_settings_running_returns_409(client, tmp_servers_root):
    """Running server short-circuits before storage.update_server is called."""
    from backend.server import storage
    from backend.server.registry import get_server_process_registry
    server = storage.create_server({
        "name": "S", "version": "1.20.1", "loader": "fabric",
        "port": 25593, "installPath": "srv-run", "memory": 4,
    })
    with patch.object(
        get_server_process_registry(), "get_status",
        return_value={"status": "running"},
    ):
        resp = client.put(
            f"/api/servers/{server['id']}/settings",
            json={"name": "Renamed"},
        )
    assert resp.status_code == 409
    assert "stop" in resp.get_json()["error"].lower()


# ---------------------------------------------------------------------------
# PUT /api/servers/<server_id>/files/content — decorators in URL mode
# ---------------------------------------------------------------------------


def test_update_server_file_content_unknown_server_returns_404(client, tmp_servers_root):
    resp = client.put(
        "/api/servers/srv_nope/files/content",
        json={"path": "server.properties", "content": "x"},
    )
    assert resp.status_code == 404


def test_update_server_file_content_missing_path_returns_400(client, tmp_servers_root):
    from backend.server import storage
    server = storage.create_server({
        "name": "S", "version": "1.20.1", "loader": "fabric",
        "port": 25594, "installPath": "srv-files", "memory": 4,
    })
    resp = client.put(
        f"/api/servers/{server['id']}/files/content",
        json={"content": "x"},  # no path
    )
    assert resp.status_code == 400
    assert "path" in resp.get_json()["error"].lower()


def test_update_server_file_content_missing_content_returns_400(client, tmp_servers_root):
    """Missing content is checked AFTER missing path — fires here with path present."""
    from backend.server import storage
    server = storage.create_server({
        "name": "S", "version": "1.20.1", "loader": "fabric",
        "port": 25595, "installPath": "srv-files-2", "memory": 4,
    })
    resp = client.put(
        f"/api/servers/{server['id']}/files/content",
        json={"path": "server.properties"},  # no content
    )
    assert resp.status_code == 400
    assert "content" in resp.get_json()["error"].lower()
