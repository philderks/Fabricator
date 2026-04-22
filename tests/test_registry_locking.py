"""C6: Destructive per-server operations must be serialized."""
from __future__ import annotations

import threading


def test_server_lock_registry_returns_same_lock_for_same_id():
    from backend.server.locks import get_server_lock

    lock_a = get_server_lock("srv_abc")
    lock_b = get_server_lock("srv_abc")
    assert lock_a is lock_b


def test_server_lock_registry_returns_different_locks_for_different_ids():
    from backend.server.locks import get_server_lock

    assert get_server_lock("srv_one") is not get_server_lock("srv_two")


def test_lock_is_reentrant_for_same_thread():
    from backend.server.locks import get_server_lock

    lock = get_server_lock("srv_reentrant")
    with lock:
        with lock:
            assert True


def test_try_acquire_returns_none_when_held_elsewhere():
    from backend.server.locks import get_server_lock, try_acquire

    lock = get_server_lock("srv_busy")
    holder_started = threading.Event()
    release = threading.Event()

    def hold():
        with lock:
            holder_started.set()
            release.wait(timeout=5)

    t = threading.Thread(target=hold, daemon=True)
    t.start()
    holder_started.wait(timeout=2)

    assert try_acquire("srv_busy") is None
    release.set()
    t.join(timeout=2)

    acquired = try_acquire("srv_busy")
    assert acquired is not None
    acquired.release()


def test_install_while_running_returns_409(client, tmp_servers_root, monkeypatch):
    """Install endpoint must 409 when another op holds the lock."""
    import json
    from pathlib import Path

    index = Path(tmp_servers_root) / "servers.json"
    index.write_text(
        json.dumps(
            [
                {
                    "id": "srv_test",
                    "name": "Test",
                    "version": "1.20.1",
                    "loader": "fabric",
                    "port": 25565,
                    "installPath": "srv_test",
                    "status": "stopped",
                }
            ]
        ),
        encoding="utf-8",
    )

    from backend.server.locks import get_server_lock
    lock = get_server_lock("srv_test")
    # Simulate another operation holding the lock.
    lock.acquire()
    try:
        resp = client.post("/api/servers/srv_test/install")
        assert resp.status_code == 409, resp.get_json()
    finally:
        lock.release()
