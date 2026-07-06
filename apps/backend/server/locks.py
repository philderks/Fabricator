"""Per-server operation locks.

One RLock per server id. Acquired by any operation that reads-then-writes
server state (start, stop, restart, install, modpack install, settings save,
file edit, backup restore, delete). Prevents races that today can leave a
server half-installed or partially deleted.

In production, Flask's ``threaded=True`` server dispatches each request on
its own thread, so contending operations show up as different threads and
``RLock``'s thread-scoped semantics are exactly right: different-thread
``acquire(blocking=False)`` returns ``False`` while same-thread re-entry
(e.g. a helper that acquires the lock again) succeeds without deadlock.
"""
from __future__ import annotations

import threading
from typing import Dict, Optional

_locks: Dict[str, threading.RLock] = {}
_locks_guard = threading.Lock()


def get_server_lock(server_id: str) -> threading.RLock:
    """Return the RLock for ``server_id`` (creates on first call)."""
    key = str(server_id)
    with _locks_guard:
        lock = _locks.get(key)
        if lock is None:
            lock = threading.RLock()
            _locks[key] = lock
        return lock


def try_acquire(server_id: str) -> Optional[threading.RLock]:
    """Non-blocking acquire. Returns the lock if acquired, ``None`` if busy.

    The caller is responsible for calling ``.release()`` — prefer using a
    ``with lock:`` block via :func:`get_server_lock` whenever blocking is OK.
    """
    lock = get_server_lock(server_id)
    if lock.acquire(blocking=False):
        return lock
    return None


def discard_lock(server_id: str) -> None:
    """Remove a lock entry (used when a server is deleted)."""
    with _locks_guard:
        _locks.pop(str(server_id), None)
