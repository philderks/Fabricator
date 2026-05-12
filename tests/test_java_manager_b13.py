"""B13: java_manager reliability fixes.

Pins the four behaviours introduced by commit B13 (partial — the
``install_progress`` half is deferred):

1. ``_parse_system_java_major`` enforces a ``timeout`` on
   ``subprocess.run(["java","-version"])`` and treats ``TimeoutExpired``
   identically to a missing binary.
2. ``_install_tasks`` evicts terminal tasks older than the retention
   window without touching active tasks.
3. ``start_install_task`` exposes a ``cancel_event`` and
   ``cancel_install_task`` flips the task to ``cancelled`` for an
   in-flight worker.
4. ``adoptium_asset_url`` (and ``download_java`` by extension) retries
   transient 5xx via the B12b ``request_with_retry`` helper.
"""
from __future__ import annotations

import re
import subprocess
import time
from unittest.mock import MagicMock, patch

import pytest
import requests

from backend.server import java_manager


_ISO_Z_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{6})?Z")


# ---------------------------------------------------------------------------
# Aktion 1: subprocess timeout
# ---------------------------------------------------------------------------


def test_parse_system_java_major_returns_none_on_timeout():
    """A wedged ``java`` binary must not hang the request thread."""
    with patch("backend.server.java_manager.subprocess.run") as mock_run:
        mock_run.side_effect = subprocess.TimeoutExpired(
            cmd=["java", "-version"], timeout=10
        )
        assert java_manager._parse_system_java_major() is None


def test_parse_system_java_major_passes_timeout_kwarg():
    """The ``timeout=`` argument must actually reach ``subprocess.run``."""
    fake_completed = subprocess.CompletedProcess(
        args=["java", "-version"], returncode=0,
        stdout="", stderr='openjdk version "21" 2023-09-19',
    )
    with patch("backend.server.java_manager.subprocess.run", return_value=fake_completed) as mock_run:
        java_manager._parse_system_java_major()
        _, kwargs = mock_run.call_args
        assert "timeout" in kwargs
        assert kwargs["timeout"] == java_manager._SYSTEM_JAVA_VERSION_TIMEOUT_SEC


def test_parse_system_java_major_returns_none_on_oserror():
    """Permission/OS errors are also gracefully mapped to None."""
    with patch("backend.server.java_manager.subprocess.run") as mock_run:
        mock_run.side_effect = OSError("permission denied")
        assert java_manager._parse_system_java_major() is None


def test_parse_system_java_major_still_returns_none_on_filenotfound():
    """Pre-B13 contract preserved: missing binary still returns None."""
    with patch("backend.server.java_manager.subprocess.run") as mock_run:
        mock_run.side_effect = FileNotFoundError()
        assert java_manager._parse_system_java_major() is None


# ---------------------------------------------------------------------------
# Aktion 2: _install_tasks Eviction
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolate_install_tasks():
    """Each test starts with a clean ``_install_tasks`` dict."""
    with java_manager._install_tasks_lock:
        java_manager._install_tasks.clear()
        java_manager._install_task_handles.clear()
    yield
    with java_manager._install_tasks_lock:
        java_manager._install_tasks.clear()
        java_manager._install_task_handles.clear()


def test_evict_old_install_tasks_drops_completed_past_retention():
    """A ``done`` task with a stale ``completed_at`` must be evicted."""
    stale_ts = time.monotonic() - (java_manager._INSTALL_TASK_RETENTION_SEC + 5)
    with java_manager._install_tasks_lock:
        java_manager._install_tasks["stale"] = {
            "status": "done",
            "completed_at": stale_ts,
        }
        java_manager._install_task_handles["stale"] = {"thread": None}

    java_manager._evict_old_install_tasks()

    with java_manager._install_tasks_lock:
        assert "stale" not in java_manager._install_tasks
        assert "stale" not in java_manager._install_task_handles


def test_evict_old_install_tasks_keeps_active_tasks():
    """Active (non-terminal) tasks must survive eviction sweeps."""
    ancient_ts = time.monotonic() - (java_manager._INSTALL_TASK_RETENTION_SEC * 100)
    with java_manager._install_tasks_lock:
        # Active task with no completed_at — must NEVER be evicted.
        java_manager._install_tasks["active"] = {
            "status": "downloading",
            "completed_at": None,
            # Even if some older code path leaked a stale created marker,
            # the eviction key is ``completed_at`` + terminal status.
            "_unused_old_ts": ancient_ts,
        }

    java_manager._evict_old_install_tasks()

    with java_manager._install_tasks_lock:
        assert "active" in java_manager._install_tasks


def test_evict_old_install_tasks_keeps_recently_completed():
    """A ``done`` task within the retention window must survive."""
    recent_ts = time.monotonic() - 5  # 5 seconds ago
    with java_manager._install_tasks_lock:
        java_manager._install_tasks["recent"] = {
            "status": "done",
            "completed_at": recent_ts,
        }

    java_manager._evict_old_install_tasks()

    with java_manager._install_tasks_lock:
        assert "recent" in java_manager._install_tasks


def test_update_task_stamps_completed_at_on_terminal_status():
    """Transitioning to ``done`` / ``error`` / ``cancelled`` records completed_at."""
    with java_manager._install_tasks_lock:
        java_manager._install_tasks["t1"] = {
            "status": "downloading",
            "completed_at": None,
        }

    java_manager._update_task("t1", status="done")

    with java_manager._install_tasks_lock:
        task = java_manager._install_tasks["t1"]
        assert task["completed_at"] is not None
        assert task["status"] == "done"


def test_update_task_does_not_overwrite_existing_completed_at():
    """Once stamped, ``completed_at`` is immutable across subsequent updates."""
    original_ts = time.monotonic() - 100
    with java_manager._install_tasks_lock:
        java_manager._install_tasks["t1"] = {
            "status": "done",
            "completed_at": original_ts,
        }

    java_manager._update_task("t1", status="error")

    with java_manager._install_tasks_lock:
        assert java_manager._install_tasks["t1"]["completed_at"] == original_ts


# ---------------------------------------------------------------------------
# Aktion 3: Background-Thread Cancel-Event
# ---------------------------------------------------------------------------


def test_cancel_install_task_unknown_returns_false():
    assert java_manager.cancel_install_task("does-not-exist") is False


def test_cancel_install_task_terminal_returns_false():
    """Terminal tasks cannot be re-cancelled."""
    import threading
    with java_manager._install_tasks_lock:
        java_manager._install_tasks["t1"] = {
            "status": "done",
            "completed_at": time.monotonic(),
        }
        java_manager._install_task_handles["t1"] = {
            "cancel_event": threading.Event(),
            "thread": None,
        }
    assert java_manager.cancel_install_task("t1") is False


def test_cancel_install_task_active_sets_event_and_status():
    """An active task gets ``cancelled`` status and the event is set."""
    import threading
    cancel_event = threading.Event()
    with java_manager._install_tasks_lock:
        java_manager._install_tasks["t1"] = {
            "status": "downloading",
            "completed_at": None,
        }
        java_manager._install_task_handles["t1"] = {
            "cancel_event": cancel_event,
            "thread": None,
        }

    assert java_manager.cancel_install_task("t1") is True
    assert cancel_event.is_set()
    with java_manager._install_tasks_lock:
        assert java_manager._install_tasks["t1"]["status"] == "cancelled"


def test_start_install_task_publishes_thread_handle_and_cancel_event():
    """``start_install_task`` records both the thread and the cancel event."""
    # Mock the install pipeline so the thread terminates immediately and
    # we can inspect the handle without hitting the network.
    with patch.object(java_manager, "download_java", side_effect=RuntimeError("stop")):
        task_id = java_manager.start_install_task(21)
        # Give the daemon thread a chance to flip status -> error.
        for _ in range(50):
            with java_manager._install_tasks_lock:
                status = java_manager._install_tasks[task_id].get("status")
            if status in java_manager._TERMINAL_STATUSES:
                break
            time.sleep(0.02)

    with java_manager._install_tasks_lock:
        handle = java_manager._install_task_handles.get(task_id)
        assert handle is not None
        assert handle["thread"] is not None
        assert handle["cancel_event"] is not None


# ---------------------------------------------------------------------------
# Aktion 4: adoptium_asset_url retry
# ---------------------------------------------------------------------------


def _http_error(status: int) -> requests.HTTPError:
    response = requests.Response()
    response.status_code = status
    return requests.HTTPError(response=response)


def test_adoptium_asset_url_retries_on_503():
    """A transient 503 on the first call is retried and succeeds on the second."""
    asset_payload = [
        {
            "binary": {
                "image_type": "jdk",
                "os": java_manager._adoptium_os_label(),
                "architecture": "x64",
                "package": {
                    "link": "https://example.invalid/jdk.tar.gz",
                    "name": "jdk.tar.gz",
                    "size": 1234,
                    "checksum": "deadbeef",
                },
            }
        }
    ]

    fail_response = MagicMock(spec=requests.Response)
    fail_response.status_code = 503
    fail_response.raise_for_status.side_effect = _http_error(503)

    ok_response = MagicMock(spec=requests.Response)
    ok_response.status_code = 200
    ok_response.raise_for_status.return_value = None
    ok_response.json.return_value = asset_payload

    with patch.object(java_manager.requests, "get", side_effect=[fail_response, ok_response]) as mock_get, \
         patch.object(java_manager.platform_utils, "arch_label", return_value="x64"), \
         patch.object(java_manager.time, "sleep"):  # speed up backoff
        result = java_manager.adoptium_asset_url(21)

    assert result["download_url"] == "https://example.invalid/jdk.tar.gz"
    assert mock_get.call_count == 2


def test_adoptium_asset_url_does_not_retry_on_404():
    """A 404 indicates a caller-side problem and must surface immediately."""
    fail_response = MagicMock(spec=requests.Response)
    fail_response.status_code = 404
    fail_response.raise_for_status.side_effect = _http_error(404)

    with patch.object(java_manager.requests, "get", return_value=fail_response) as mock_get, \
         patch.object(java_manager.time, "sleep"):
        with pytest.raises(RuntimeError, match="HTTP 404"):
            java_manager.adoptium_asset_url(21)

    assert mock_get.call_count == 1


def test_adoptium_asset_url_retries_on_connection_error():
    """ConnectionError is transient; the helper retries it."""
    asset_payload = [
        {
            "binary": {
                "image_type": "jdk",
                "os": java_manager._adoptium_os_label(),
                "architecture": "x64",
                "package": {
                    "link": "https://example.invalid/jdk.tar.gz",
                    "name": "jdk.tar.gz",
                    "size": 1234,
                    "checksum": "deadbeef",
                },
            }
        }
    ]

    ok_response = MagicMock(spec=requests.Response)
    ok_response.status_code = 200
    ok_response.raise_for_status.return_value = None
    ok_response.json.return_value = asset_payload

    with patch.object(
        java_manager.requests, "get",
        side_effect=[requests.ConnectionError("net down"), ok_response],
    ) as mock_get, \
         patch.object(java_manager.platform_utils, "arch_label", return_value="x64"), \
         patch.object(java_manager.time, "sleep"):
        result = java_manager.adoptium_asset_url(21)

    assert result["filename"] == "jdk.tar.gz"
    assert mock_get.call_count == 2


# ---------------------------------------------------------------------------
# ISO-Z wire-format pin
# ---------------------------------------------------------------------------


def test_now_iso_matches_iso_z_wire_format():
    """``_now_iso`` is pinned to ``YYYY-MM-DDTHH:MM:SS[.ffffff]Z``.

    Install-task records (``created_at``, ``updated_at``) flow through
    this helper. Frontend renders these strings verbatim.
    """
    ts = java_manager._now_iso()
    assert _ISO_Z_RE.fullmatch(ts), f"_now_iso not ISO-Z: {ts!r}"


def test_run_install_task_walls_clock_cap_transitions_to_error(monkeypatch):
    """A task whose ``started_at`` is past the cap transitions to ``error``.

    Pins the wall-clock-cap branch of ``_check_cancel_or_timeout``: when
    ``time.monotonic() - started_at > _INSTALL_TASK_MAX_RUNTIME_SEC`` the
    first check raises, the cancel event is set, and the task's status
    flips to ``error`` with the cap message preserved in ``error``.
    """
    import threading

    task_id = "t_cap"
    with java_manager._install_tasks_lock:
        java_manager._install_tasks[task_id] = {
            "status": "queued",
            "downloaded": 0,
            "total": 0,
            "completed_at": None,
        }

    cancel_event = threading.Event()
    # Pin started_at far enough in the past that the FIRST cap check fires.
    started_at = time.monotonic() - (java_manager._INSTALL_TASK_MAX_RUNTIME_SEC + 100)

    # effective_install_major is pure; no patching needed. download_java would
    # never be called because the first _check_cancel_or_timeout raises.
    java_manager._run_install_task(task_id, major=21, cancel_event=cancel_event, started_at=started_at)

    with java_manager._install_tasks_lock:
        task = java_manager._install_tasks[task_id]
    assert task["status"] == "error", task
    assert "wall-clock cap" in (task.get("error") or "").lower()
    assert cancel_event.is_set()
