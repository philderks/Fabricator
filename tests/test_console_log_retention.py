"""Console log retention across a server restart.

Restarting used to clear the stdout/stderr buffers outright, so the output that
explained a crash was destroyed by the restart used to recover from it. The
previous run's tail is now demoted into separate buffers and served ahead of the
current run, behind a boundary marker.

The separation matters beyond presentation: _spawn_process's immediate-exit
diagnostic and wait_for_log()/_stdout_total must keep seeing ONLY the current
run, or a server that dies before printing anything gets diagnosed from the
previous run's output.
"""
import subprocess

from backend.server.manager import ServerManager


def _manager_with_pipes(script: str = "sleep 0.2") -> ServerManager:
    """A manager holding a live piped process, ready for _start_log_streams()."""
    mgr = ServerManager(cwd=".", command=["true"])
    mgr._process = subprocess.Popen(
        ["sh", "-c", script],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return mgr


def _seed_previous_run(mgr: ServerManager, count: int = 3) -> None:
    with mgr._buffer_lock:
        mgr._stdout_buffer = [(f"2026-08-05T08:00:0{i}Z", f"old {i}\n") for i in range(count)]
        mgr._stderr_buffer = [("2026-08-05T08:00:09Z", "old boom\n")]
        mgr._stdout_total = count


def _texts(entries):
    return [e["text"] for e in entries]


def test_restart_demotes_previous_run_instead_of_dropping_it():
    mgr = _manager_with_pipes()
    _seed_previous_run(mgr)
    try:
        mgr._start_log_streams()
        assert _texts([{"text": t} for _, t in mgr._prev_stdout_buffer]) == [
            "old 0\n", "old 1\n", "old 2\n",
        ]
        # Live buffers start empty so the current run is measured from zero.
        assert mgr._stdout_buffer == []
        assert mgr._stderr_buffer == []
        assert mgr._stdout_total == 0
    finally:
        mgr._process.wait(timeout=5)


def test_previous_run_tail_is_capped():
    mgr = _manager_with_pipes()
    overflow = ServerManager.PREV_RUN_LINES + 50
    with mgr._buffer_lock:
        mgr._stdout_buffer = [("ts", f"line {i}\n") for i in range(overflow)]
    try:
        mgr._start_log_streams()
        assert len(mgr._prev_stdout_buffer) == ServerManager.PREV_RUN_LINES
        # Kept the NEWEST lines — the tail, not the head.
        assert mgr._prev_stdout_buffer[-1][1] == f"line {overflow - 1}\n"
    finally:
        mgr._process.wait(timeout=5)


def test_immediate_exit_diagnostic_ignores_previous_run():
    """The regression guard for retention: a process that dies silently must not
    be explained using the previous run's output."""
    mgr = ServerManager(cwd=".", command=["true"])
    _seed_previous_run(mgr)
    with mgr._lock:  # mimic start(), which holds the lock across _spawn_process
        started, message = mgr._spawn_process(["sh", "-c", "exit 3"])
    assert started is False
    assert "exited immediately (code 3)" in message
    assert "old" not in message


def test_immediate_exit_diagnostic_still_reports_current_run():
    mgr = ServerManager(cwd=".", command=["true"])
    _seed_previous_run(mgr)
    with mgr._lock:
        started, message = mgr._spawn_process(
            ["sh", "-c", "echo 'Unable to access jarfile server.jar' >&2; exit 1"]
        )
    assert started is False
    assert "Unable to access jarfile" in message
    assert "old" not in message


# --- _serialize_run_tail ----------------------------------------------------

def test_serialize_orders_previous_then_boundary_then_current():
    previous = [("2026-08-05T08:00:00Z", "old\n")]
    current = [("2026-08-05T09:00:00Z", "new\n")]
    out = ServerManager._serialize_run_tail(previous, current, limit=100, boundary=True)
    assert _texts(out) == ["old\n", "Server restarted", "new\n"]
    assert out[1]["boundary"] is True


def test_boundary_carries_sortable_timestamp():
    """A null ts here would disable the frontend's stdout/stderr interleave,
    which only sorts when EVERY line has a parseable timestamp."""
    previous = [("2026-08-05T08:00:00Z", "old\n")]
    current = [("2026-08-05T09:00:00Z", "new\n")]
    out = ServerManager._serialize_run_tail(previous, current, limit=100, boundary=True)
    # Borrows the first current-run ts so it sorts immediately before it.
    assert out[1]["ts"] == "2026-08-05T09:00:00Z"

    # With no current-run lines yet, falls back to the last previous-run ts.
    out = ServerManager._serialize_run_tail(previous, [], limit=100, boundary=True)
    assert out[-1]["ts"] == "2026-08-05T08:00:00Z"


def test_no_boundary_without_a_previous_run():
    current = [("ts", "new\n")]
    out = ServerManager._serialize_run_tail([], current, limit=100, boundary=True)
    assert _texts(out) == ["new\n"]


def test_boundary_suppressed_when_not_requested():
    """stderr passes boundary=False; two markers would render two dividers in a
    console that interleaves the streams."""
    previous = [("ts", "old\n")]
    current = [("ts", "new\n")]
    out = ServerManager._serialize_run_tail(previous, current, limit=100)
    assert _texts(out) == ["old\n", "new\n"]


def test_limit_drops_oldest_first():
    previous = [("ts", f"old {i}\n") for i in range(3)]
    current = [("ts", f"new {i}\n") for i in range(3)]
    out = ServerManager._serialize_run_tail(previous, current, limit=4, boundary=True)
    # 3 old + marker + 3 new = 7; the newest 4 survive.
    assert _texts(out) == ["Server restarted", "new 0\n", "new 1\n", "new 2\n"]


def test_busy_current_run_evicts_previous_run_entirely():
    previous = [("ts", "old\n")]
    current = [("ts", f"new {i}\n") for i in range(10)]
    out = ServerManager._serialize_run_tail(previous, current, limit=5, boundary=True)
    assert all(e["text"].startswith("new") for e in out)
    assert not any(e.get("boundary") for e in out)


def test_non_positive_limit_returns_nothing():
    """Guards the slice: entries[-0:] would otherwise return the whole list."""
    previous = [("ts", "old\n")]
    current = [("ts", "new\n")]
    assert ServerManager._serialize_run_tail(previous, current, limit=0, boundary=True) == []
    assert ServerManager._serialize_run_tail(previous, current, limit=-5, boundary=True) == []


def test_tail_logs_serves_both_runs():
    mgr = ServerManager(cwd=".", command=["true"])
    with mgr._buffer_lock:
        mgr._prev_stdout_buffer = [("2026-08-05T08:00:00Z", "old\n")]
        mgr._stdout_buffer = [("2026-08-05T09:00:00Z", "new\n")]
    payload = mgr.tail_logs(limit=100)
    assert _texts(payload["stdout"]) == ["old\n", "Server restarted", "new\n"]
    assert payload["running"] is False
