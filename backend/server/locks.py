"""Per-server operation locks.

One lock per server id.  The lock is reentrant for the same thread (so that
internal helpers called from a route handler that already holds the lock do
not deadlock), AND ``try_acquire`` returns ``None`` even when the *same* OS
thread already holds it at the route-entry level.

This is achieved with ``_ServerLock``:

* A plain ``Lock`` (*busy gate*) is the serialisation primitive.  It is NOT
  reentrant — a second ``acquire()`` from the same thread will block.
* A thread-local counter tracks how many times the current thread has entered
  via ``acquire()``/``__enter__``.  On the second (and subsequent) enter the
  busy gate is *skipped* (reentrancy) and only the counter is incremented.
  On ``release()``/``__exit__`` the counter is decremented; the busy gate is
  released only when the counter reaches zero.

``try_acquire`` attempts a **non-blocking** acquire of the busy gate.  If the
gate is held — whether by the same thread or another — it returns ``None``.
This is the behaviour the test suite requires: the test thread holds the gate
and then calls ``try_acquire`` (via the synchronous Flask test client on the
same OS thread), expecting ``None``.

On success ``try_acquire`` returns the lock with the counter already at 1 so
that helpers using ``with get_server_lock(id):`` re-enter correctly.
"""
from __future__ import annotations

import threading
from typing import Dict, Optional


class _ServerLock:
    """Thread-aware reentrant lock with a non-reentrant external busy gate."""

    def __init__(self) -> None:
        self._gate = threading.Lock()        # plain, non-reentrant
        self._local = threading.local()      # per-thread depth counter

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _depth(self) -> int:
        return getattr(self._local, 'depth', 0)

    def _set_depth(self, d: int) -> None:
        self._local.depth = d

    # ------------------------------------------------------------------
    # Public interface (used by get_server_lock / with lock:)
    # ------------------------------------------------------------------

    def acquire(self, blocking: bool = True, timeout: float = -1) -> bool:
        depth = self._depth()
        if depth > 0:
            # Already held by this thread — reentrant path, skip gate.
            self._set_depth(depth + 1)
            return True
        # First acquisition: must take the gate.
        if timeout != -1:
            acquired = self._gate.acquire(blocking=blocking, timeout=timeout)
        else:
            acquired = self._gate.acquire(blocking=blocking)
        if acquired:
            self._set_depth(1)
        return acquired

    def release(self) -> None:
        depth = self._depth()
        if depth <= 0:
            raise RuntimeError('release() called on unheld lock')
        if depth == 1:
            self._set_depth(0)
            self._gate.release()
        else:
            self._set_depth(depth - 1)

    def __enter__(self) -> "_ServerLock":
        self.acquire()
        return self

    def __exit__(self, *_) -> None:
        self.release()

    # ------------------------------------------------------------------
    # Used by try_acquire: non-blocking gate check, bypasses reentrancy
    # ------------------------------------------------------------------

    def _try_acquire_nonreentrant(self) -> bool:
        """Always attempt the gate non-blocking, even if this thread holds it.

        Returns True (and increments depth) only if the gate was NOT
        previously held at all (depth == 0 AND gate acquired).
        Returns False if the gate is already held by *anyone*, including
        the current thread.
        """
        # If this thread already holds it (depth > 0), the gate would succeed
        # (reentrant), but we DON'T want that — report busy.
        if self._depth() > 0:
            return False
        acquired = self._gate.acquire(blocking=False)
        if acquired:
            self._set_depth(1)
        return acquired


_locks: Dict[str, _ServerLock] = {}
_locks_guard = threading.Lock()


def get_server_lock(server_id: str) -> _ServerLock:
    """Return the lock for ``server_id`` (creates on first call).

    The returned lock is reentrant for the same thread: calling ``acquire()``
    (or ``with lock:``) multiple times from the same thread succeeds, with
    matching ``release()`` calls needed to fully release.
    """
    key = str(server_id)
    with _locks_guard:
        lock = _locks.get(key)
        if lock is None:
            lock = _ServerLock()
            _locks[key] = lock
        return lock


def try_acquire(server_id: str) -> Optional["_ServerLock"]:
    """Non-blocking acquire.  Returns the lock if acquired, ``None`` if busy.

    Unlike ``get_server_lock().acquire(blocking=False)`` this does **not**
    re-enter even from the same OS thread.  This makes it safe to use as a
    concurrency gate at route-handler entry points: the route handler's busy
    status is visible to the same-thread synchronous Flask test client.

    The caller must call ``.release()`` on the returned lock::

        lock = try_acquire(server_id)
        if lock is None:
            return jsonify({'error': '...'}), 409
        try:
            ...
        finally:
            lock.release()
    """
    lock = get_server_lock(server_id)
    if lock._try_acquire_nonreentrant():
        return lock
    return None


def discard_lock(server_id: str) -> None:
    """Remove a lock entry (used when a server is deleted)."""
    with _locks_guard:
        _locks.pop(str(server_id), None)
