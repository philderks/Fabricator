"""ServerManager concurrency guards.

- stop()/start() race: during stop()'s unlocked drain, self._process is cleared
  (is_running reads False) while the JVM is still up; start() must refuse so no
  second process launches on the same world.
- wait_for_log() must keep working after the stdout buffer saturates at
  MAX_LOG_LINES and every append front-truncates (absolute indices stop
  advancing; a monotonic counter does not).
"""
import subprocess
import threading
import time

from backend.server.manager import ServerManager


def _wait(cond, timeout: float = 3.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if cond():
            return True
        time.sleep(0.01)
    return False


def test_start_refused_while_stop_is_draining():
    mgr = ServerManager(cwd=".", command=["true"])

    release = threading.Event()

    class FakeProc:
        stdin = None

        def poll(self):
            return None  # still alive throughout the drain

        def wait(self, timeout=None):
            if not release.wait(timeout):
                raise subprocess.TimeoutExpired(cmd="server", timeout=timeout)
            return 0

        def terminate(self):
            pass

        def kill(self):
            pass

    mgr._process = FakeProc()

    stopper = threading.Thread(target=mgr.stop, daemon=True)
    stopper.start()
    try:
        assert _wait(lambda: mgr._stopping), "stop() never entered draining state"
        assert mgr.is_running is False  # process cleared during drain
        result = mgr.start()
        assert result["status"] != "running", result
        assert "stopping" in result["message"].lower()
    finally:
        release.set()
        stopper.join(timeout=5)

    # Once the drain finishes the guard clears and start() is allowed again.
    assert _wait(lambda: mgr._stopping is False)


def test_wait_for_log_matches_after_buffer_saturation():
    mgr = ServerManager(cwd=".", command=["true"])
    n = ServerManager.MAX_LOG_LINES
    with mgr._buffer_lock:
        mgr._stdout_buffer = [("ts", f"noise {i}\n") for i in range(n)]
        mgr._stdout_total = n

    def emit():
        time.sleep(0.05)
        with mgr._buffer_lock:  # same lock the real _stream append uses
            mgr._stdout_buffer.append(("ts", "Saved the game\n"))
            if len(mgr._stdout_buffer) > n:  # front-truncate; length stays at n
                del mgr._stdout_buffer[: len(mgr._stdout_buffer) - n]
            mgr._stdout_total += 1

    t = threading.Thread(target=emit)
    t.start()
    try:
        assert mgr.wait_for_log(r"Saved the game", timeout=3.0) is True
    finally:
        t.join()

    # Buffer stayed capped — proves the saturation/truncation path was exercised.
    assert len(mgr._stdout_buffer) == n


def test_spawn_process_immediate_exit_captures_stderr_tail():
    """A process that exits immediately with a stderr diagnostic must surface
    that tail in the failure message. Regression guard: the stream append must
    stay lock-free — start()/_spawn_process hold self._lock across the 0.5s
    probe window, so an append that needed the lock would leave the tail empty
    and the user would get a bare 'exited immediately (code 1)'."""
    mgr = ServerManager(cwd=".", command=["true"])
    cmd = ["sh", "-c", "echo 'Unable to access jarfile server.jar' >&2; exit 1"]
    with mgr._lock:  # mimic start(), which holds the lock across _spawn_process
        started, message = mgr._spawn_process(cmd)
    assert started is False
    assert "Unable to access jarfile" in message, message
