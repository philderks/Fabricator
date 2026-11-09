"""Which servers use each managed Java runtime (#109, "Remove unused").

``used_by`` follows the same resolver a start uses, so a runtime is only
reported unused when no server runs on it or would start on it.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

# Imported inside each test: test_app_factory drops backend modules from
# sys.modules, and a patch on a stale module object would not reach the routes.


@pytest.fixture
def jdks(tmp_servers_root):
    """Stub managed JDKs 8, 17 and 21; returns their java binaries by major."""
    from backend.server import java_manager
    binaries = {}
    for major in (8, 17, 21):
        binary = java_manager.managed_java_binary_path(major)
        binary.parent.mkdir(parents=True)
        binary.write_text("stub")
        binaries[major] = binary
    return binaries


def _server(tmp_servers_root, name, **fields):
    from backend.server import storage
    install_path = tmp_servers_root / "servers" / name
    install_path.mkdir()
    return storage.create_server({
        "name": name, "version": "1.20.1", "loader": "vanilla",
        "installPath": str(install_path), **fields,
    })


def _used_by(client):
    resp = client.get("/api/java/installed")
    assert resp.status_code == 200
    return {entry["major"]: entry["used_by"] for entry in resp.get_json()["managed"]}


def test_automatic_and_explicit_java_count_as_used(client, tmp_servers_root, jdks):
    from backend.server import java_manager
    _server(tmp_servers_root, "auto")  # 1.20.1 needs 17, no PATH java
    _server(tmp_servers_root, "pinned", javaPath=str(jdks[21]))
    with patch.object(java_manager, "_parse_system_java_major", return_value=None):
        assert _used_by(client) == {8: [], 17: ["auto"], 21: ["pinned"]}


def test_a_fitting_path_java_leaves_the_managed_one_unused(client, tmp_servers_root, jdks):
    from backend.server import java_manager
    _server(tmp_servers_root, "auto")
    with patch.object(java_manager, "_parse_system_java_major", return_value=21), \
            patch("shutil.which", return_value=None):
        assert _used_by(client) == {8: [], 17: [], 21: []}


def test_a_running_server_keeps_the_java_it_started_on(client, tmp_servers_root, jdks):
    from backend.server import java_manager
    from backend.server.registry import get_server_process_registry
    server = _server(tmp_servers_root, "running")
    get_server_process_registry()._instances[server["id"]] = SimpleNamespace(
        is_running=True, _java_executable=lambda: str(jdks[8]),
    )
    with patch.object(java_manager, "_parse_system_java_major", return_value=None):
        assert _used_by(client) == {8: ["running"], 17: [], 21: []}
