"""Pre-start command (#103): a shell command run before every server start.

Built for packwiz-style modpack syncs. The command's output opens the run's
console, a failure or timeout keeps the server stopped, and the settings route
validates it (one line) and refuses it in managed mode.
"""
from __future__ import annotations

import sys
import time

import pytest

from backend.server.manager import ServerManager

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="uses POSIX shell commands")


def _manager(tmp_path) -> ServerManager:
    mgr = ServerManager(cwd=str(tmp_path), command=["sh", "-c", "sleep 5"])
    mgr.probe_java = lambda: {"available": True, "major_version": 21, "message": "java 21", "java_exec": "java"}
    return mgr


def _stdout(mgr: ServerManager) -> list[str]:
    return [text for _, text in mgr._stdout_buffer]


def test_success_runs_in_server_folder_then_starts_with_output_kept(tmp_path):
    mgr = _manager(tmp_path)
    try:
        result = mgr.start(pre_start_command="pwd; echo synced")
        assert result["status"] == "running", result
        lines = _stdout(mgr)
        # The pre-start output opens this run; spawning the server must not
        # demote it to the "previous run" tail.
        assert lines[:3] == [
            "[pre-start] Running pre-start command\n",
            f"[pre-start] {tmp_path}\n",
            "[pre-start] synced\n",
        ]
    finally:
        mgr.stop()


def test_failure_keeps_server_stopped(tmp_path):
    mgr = _manager(tmp_path)
    result = mgr.start(pre_start_command="echo nope; exit 3")
    assert result["status"] == "stopped"
    assert "exit code 3" in result["message"]
    assert mgr._process is None
    assert "[pre-start] nope\n" in _stdout(mgr)


def test_timeout_kills_the_whole_tree(tmp_path):
    mgr = _manager(tmp_path)
    mgr.PRE_START_TIMEOUT_SEC = 1
    began = time.monotonic()
    # The sleep is a child of the shell and holds the output pipe open; only
    # killing the tree lets the start return.
    result = mgr.start(pre_start_command="sleep 30; echo late")
    assert time.monotonic() - began < 10
    assert result["status"] == "stopped"
    assert "timed out" in result["message"]
    assert mgr._process is None


def test_concurrent_start_is_refused_while_pre_start_runs(tmp_path):
    mgr = _manager(tmp_path)
    mgr._pre_starting = True
    result = mgr.start(pre_start_command="echo hi")
    assert result["status"] == "stopped"
    assert "already running" in result["message"]


# --------------------------------------------------------------------------- #
# Settings route
# --------------------------------------------------------------------------- #

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
    (tmp_servers_root / "servers" / path).mkdir(parents=True, exist_ok=True)
    return server["id"]


def test_settings_stores_trimmed_command(client, app, tmp_servers_root):
    sid = _make_server(app, tmp_servers_root, 25961, "ps-ok")
    resp = client.put(f"/api/servers/{sid}/settings", json={"preStartCommand": "  sh sync.sh  "})
    assert resp.status_code == 200, resp.get_json()
    from backend.server import storage

    with app.app_context():
        assert storage.get_server(sid)["preStartCommand"] == "sh sync.sh"


@pytest.mark.parametrize("value", ["a\nb", "a\rb", 5, "x" * 2001])
def test_settings_rejects_invalid_command(client, app, tmp_servers_root, value):
    sid = _make_server(app, tmp_servers_root, 25962, "ps-bad")
    resp = client.put(f"/api/servers/{sid}/settings", json={"preStartCommand": value})
    assert resp.status_code == 400
    assert "Pre-start command" in resp.get_json()["error"]


def test_managed_rejects_pre_start_command(client, app, tmp_servers_root, monkeypatch):
    sid = _make_server(app, tmp_servers_root, 25963, "ps-managed")
    monkeypatch.setenv("FABRICATOR_MANAGED", "1")
    resp = client.put(f"/api/servers/{sid}/settings", json={"preStartCommand": "sh evil.sh"})
    assert resp.status_code == 400
    assert "preStartCommand" in resp.get_json()["error"]
