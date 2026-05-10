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


def test_discard_lock_is_noop_for_unknown_id():
    """discard_lock on a never-seen id must not raise."""
    from backend.server.locks import discard_lock

    # Should be a clean no-op even if the registry has no entry for this id.
    discard_lock("srv_never_existed_xyz")


def test_discard_lock_drops_entry_so_next_get_returns_fresh_lock():
    """After discard_lock, get_server_lock for the same id returns a NEW RLock.

    This mirrors the production flow in routes.py:847 (delete_server_route):
    after the server is deleted, its lock entry is dropped so a recreated
    server with the same id starts with a fresh lock — not a stale handle.
    """
    from backend.server.locks import discard_lock, get_server_lock, try_acquire

    server_id = "srv_discard_recycle"
    original = get_server_lock(server_id)
    acquired = try_acquire(server_id)
    assert acquired is original
    acquired.release()

    discard_lock(server_id)

    fresh = get_server_lock(server_id)
    assert fresh is not original


def test_discard_lock_while_held_does_not_break_holding_thread():
    """discard_lock dropping the registry entry must not invalidate a held lock.

    A thread already inside ``with lock:`` keeps a direct Python reference to
    the RLock — discarding the registry entry only forgets the *mapping*,
    not the object. The holder must finish cleanly. A subsequent
    ``get_server_lock`` for the same id returns a *different* lock because
    the registry now creates a fresh one.
    """
    from backend.server.locks import discard_lock, get_server_lock

    server_id = "srv_discard_while_held"
    held_lock = get_server_lock(server_id)

    holder_started = threading.Event()
    release_holder = threading.Event()
    holder_finished = threading.Event()

    def hold():
        with held_lock:
            holder_started.set()
            release_holder.wait(timeout=5)
        holder_finished.set()

    t = threading.Thread(target=hold, daemon=True)
    t.start()
    try:
        assert holder_started.wait(timeout=2)

        # Discard while another thread holds the lock — must not raise.
        discard_lock(server_id)

        # The registry forgot the mapping, so a fresh lookup returns a new lock.
        replacement = get_server_lock(server_id)
        assert replacement is not held_lock
    finally:
        release_holder.set()
        t.join(timeout=2)

    assert holder_finished.is_set()


def test_install_returns_409_when_lock_held_by_other_thread(client, tmp_servers_root):
    """Install endpoint must 409 when another thread already holds the lock.

    The lock MUST be held by a different thread than the one issuing the
    request — otherwise the request thread (which is the same as the test
    thread under Flask's synchronous test client) would reentrantly acquire
    the RLock and the 409 path would never trigger. In production Flask's
    threaded=True dispatch naturally puts contending operations on
    different threads, so this mirrors real usage.
    """
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
    holder_started = threading.Event()
    release = threading.Event()

    def hold():
        with lock:
            holder_started.set()
            release.wait(timeout=5)

    holder = threading.Thread(target=hold, daemon=True)
    holder.start()
    try:
        assert holder_started.wait(timeout=2)
        resp = client.post("/api/servers/srv_test/install")
        assert resp.status_code == 409, resp.get_json()
    finally:
        release.set()
        holder.join(timeout=2)
