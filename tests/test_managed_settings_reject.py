"""C2 — managed settings-override reject.

Under FABRICATOR_MANAGED, PUT /api/servers/<id>/settings rejects `command`,
`javaPath`, `jvmArgs`, and the whole `launch` object (installer-owned) with an
explicit 4xx naming the field — no silent strip. Off-flag the guard does not
fire, though the values are still validated on their own merits (#54).
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
    """Off-flag, the managed guard does not fire for these keys.

    `javaPath` is a real executable here because the settings route validates
    the value once it gets past the managed guard (#54) — the point of this
    test is that the guard stays out of the way, not that any value is
    accepted. `sys.executable` is simply a path guaranteed to exist and be
    executable on whatever runs the suite.
    """
    import sys

    sid = _make_server(app, tmp_servers_root, 25905, "e")
    monkeypatch.delenv("FABRICATOR_MANAGED", raising=False)
    resp = client.put(
        f"/api/servers/{sid}/settings",
        json={"javaPath": sys.executable, "launch": {"type": "jar"}},
    )
    assert resp.status_code == 200, resp.get_json()


def test_managed_rejects_jvm_args(client, app, tmp_servers_root, monkeypatch):
    """Per-server launch flags are as installer-owned as javaPath under managed
    mode — a tenant must not be able to hand the JVM its own arguments."""
    sid = _make_server(app, tmp_servers_root, 25906, "f")
    monkeypatch.setenv("FABRICATOR_MANAGED", "1")
    resp = client.put(f"/api/servers/{sid}/settings", json={"jvmArgs": "-XX:+UseZGC"})
    assert resp.status_code == 400
    assert "jvmArgs" in resp.get_json().get("error", "")
