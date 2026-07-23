"""C2 — managed settings-override reject.

Under FABRICATOR_MANAGED, PUT /api/servers/<id>/settings rejects `command`,
`javaPath`, and the whole `launch` object (installer-owned) with an explicit
4xx naming the field — no silent strip. Off-flag they pass through unchanged.
"""
from __future__ import annotations


def _make_server(app, tmp_servers_root, port, path):
    from backend.server import storage

    with app.app_context():
        server = storage.create_server({
            "name": path,
            "version": "1.21.4",
            "loader": "paper",
            "port": port,
            "installPath": path,
        })
    # install dir must exist so a passing PUT can write server.properties
    (tmp_servers_root / "servers" / path).mkdir(parents=True, exist_ok=True)
    return server["id"]


def test_managed_rejects_command(client, app, tmp_servers_root, monkeypatch):
    sid = _make_server(app, tmp_servers_root, 25901, "a")
    monkeypatch.setenv("FABRICATOR_MANAGED", "1")
    resp = client.put(f"/api/servers/{sid}/settings", json={"command": "java -Xmx99G -jar x.jar"})
    assert resp.status_code == 400
    assert "command" in resp.get_json().get("error", "")


def test_managed_rejects_java_path(client, app, tmp_servers_root, monkeypatch):
    sid = _make_server(app, tmp_servers_root, 25902, "b")
    monkeypatch.setenv("FABRICATOR_MANAGED", "1")
    resp = client.put(f"/api/servers/{sid}/settings", json={"javaPath": "/evil/java"})
    assert resp.status_code == 400
    assert "javaPath" in resp.get_json().get("error", "")


def test_managed_rejects_launch_object(client, app, tmp_servers_root, monkeypatch):
    sid = _make_server(app, tmp_servers_root, 25903, "c")
    monkeypatch.setenv("FABRICATOR_MANAGED", "1")
    resp = client.put(
        f"/api/servers/{sid}/settings",
        json={"launch": {"type": "args_file", "args_file": "evil.txt"}},
    )
    assert resp.status_code == 400
    assert "launch" in resp.get_json().get("error", "")


def test_managed_allows_benign_settings(client, app, tmp_servers_root, monkeypatch):
    sid = _make_server(app, tmp_servers_root, 25904, "d")
    monkeypatch.setenv("FABRICATOR_MANAGED", "1")
    resp = client.put(f"/api/servers/{sid}/settings", json={"memory": 4, "difficulty": "hard"})
    assert resp.status_code == 200, resp.get_json()


def test_unmanaged_passes_forbidden_keys_through(client, app, tmp_servers_root, monkeypatch):
    sid = _make_server(app, tmp_servers_root, 25905, "e")
    monkeypatch.delenv("FABRICATOR_MANAGED", raising=False)
    resp = client.put(
        f"/api/servers/{sid}/settings",
        json={"javaPath": "/custom/java", "launch": {"type": "jar"}},
    )
    assert resp.status_code == 200, resp.get_json()
