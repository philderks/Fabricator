"""Concurrent installs of the SAME Java major must serialize (they share the
fixed download path + managed target dir and would corrupt each other), while
each request stays an independent, independently-cancellable task."""
import threading
import time
from pathlib import Path

from backend.server import java_manager as jm


def _reset():
    with jm._install_tasks_lock:
        jm._install_tasks.clear()
        jm._install_task_handles.clear()
    with jm._major_install_locks_guard:
        jm._major_install_locks.clear()


def test_same_major_installs_do_not_run_concurrently(monkeypatch):
    state = {"in_download": 0, "max": 0}
    guard = threading.Lock()
    first_in = threading.Event()
    release = threading.Event()

    def fake_download(major, progress_callback=None, cancel_event=None):
        with guard:
            state["in_download"] += 1
            state["max"] = max(state["max"], state["in_download"])
        first_in.set()
        release.wait(timeout=5)
        with guard:
            state["in_download"] -= 1
        return Path("/fake/archive.tar.gz")

    monkeypatch.setattr(jm, "download_java", fake_download)
    monkeypatch.setattr(jm, "install_java", lambda major, archive: "/fake/java")

    _reset()
    try:
        id1 = jm.start_install_task(17)
        assert first_in.wait(timeout=3), "first install never entered download"
        id2 = jm.start_install_task(17)

        # id2 must be a distinct, independently-cancellable task...
        assert id2 != id1
        # ...and must be blocked on the per-major lock, NOT downloading in
        # parallel with id1 (give its worker a moment to reach the lock).
        time.sleep(0.3)
        assert state["max"] == 1, "two same-major installs ran download concurrently"

        release.set()

        # Both tasks reach a terminal state (id2 runs after id1 releases).
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            with jm._install_tasks_lock:
                pending = [
                    t for t in jm._install_tasks.values()
                    if t.get("status") not in jm._TERMINAL_STATUSES
                ]
            if not pending:
                break
            time.sleep(0.02)
        assert not pending, "install tasks did not finish"
        assert state["max"] == 1  # never overlapped
    finally:
        release.set()
        _reset()
