"""Per-server install progress store.

Mirror of backend/modrinth/routes.py:_install_progress for loader installs.
T1 only verifies the store mechanics. The phase vocabulary is set by T2
when concrete loaders start emitting; T1 treats phase strings as opaque.
"""
from __future__ import annotations

import re
import threading
import time

from backend.server.install_progress import update, get, clear, is_active


_ISO_Z_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{6})?Z")


def setup_function(_):
    """Each test starts with an empty store."""
    # Tests don't share state, but the module is global. Clear known keys.
    for sid in ("srv_test_1", "srv_test_2", "srv_concurrent"):
        clear(sid)


def test_update_and_get_roundtrip():
    update("srv_test_1", phase="starting", server_id="srv_test_1")
    snapshot = get("srv_test_1")

    assert snapshot["phase"] == "starting"
    assert snapshot["server_id"] == "srv_test_1"
    assert "updated_at" in snapshot


def test_get_nonexistent_returns_empty_dict():
    assert get("does-not-exist") == {}


def test_clear_nonexistent_is_noop():
    clear("does-not-exist")  # Must not raise.
    assert get("does-not-exist") == {}


def test_update_merges_kwargs_preserving_existing():
    update("srv_test_1", phase="starting", server_id="srv_test_1")
    update("srv_test_1", bytes_done=512, bytes_total=4096)

    snapshot = get("srv_test_1")
    # Earlier kwargs are preserved.
    assert snapshot["phase"] == "starting"
    assert snapshot["server_id"] == "srv_test_1"
    # Later kwargs are merged in.
    assert snapshot["bytes_done"] == 512
    assert snapshot["bytes_total"] == 4096


def test_updated_at_is_monotonically_non_decreasing():
    update("srv_test_1", phase="starting")
    first_ts = get("srv_test_1")["updated_at"]
    time.sleep(0.005)  # 5ms — enough for the ISO timestamp to advance.
    update("srv_test_1", phase="resolving_versions")
    second_ts = get("srv_test_1")["updated_at"]

    assert second_ts >= first_ts


def test_is_active_for_phases():
    # No entry → not active.
    assert is_active("srv_test_1") is False

    # Phase set but not terminal → active.
    update("srv_test_1", phase="starting")
    assert is_active("srv_test_1") is True

    update("srv_test_1", phase="downloading_installer")
    assert is_active("srv_test_1") is True

    # Terminal phases → not active.
    update("srv_test_1", phase="done")
    assert is_active("srv_test_1") is False

    update("srv_test_2", phase="failed", error="boom")
    assert is_active("srv_test_2") is False


def test_concurrent_updates_do_not_corrupt_store():
    """Multiple threads writing to different keys must not race."""
    def writer(server_id: str, count: int):
        for i in range(count):
            update(server_id, bytes_done=i, phase="downloading_installer")

    t1 = threading.Thread(target=writer, args=("srv_test_1", 200))
    t2 = threading.Thread(target=writer, args=("srv_test_2", 200))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    # Both keys exist with the final write visible.
    assert get("srv_test_1")["bytes_done"] == 199
    assert get("srv_test_1")["phase"] == "downloading_installer"
    assert get("srv_test_2")["bytes_done"] == 199


def test_updated_at_matches_iso_z_wire_format():
    """``updated_at`` wire format is pinned: ``YYYY-MM-DDTHH:MM:SS[.ffffff]Z``.

    Mirror in the frontend renders this string verbatim — drift to e.g.
    ``+00:00`` suffix or naive ISO would break the consumer surface.
    """
    update("srv_test_1", phase="starting")
    ts = get("srv_test_1")["updated_at"]
    assert _ISO_Z_RE.fullmatch(ts), f"updated_at not ISO-Z: {ts!r}"


def test_install_base_install_signature_accepts_progress_callback():
    """InstallerBase.install signature must accept progress_callback=None.

    Verified via FabricInstaller (any concrete subclass would do). Backward-
    compat anchor: existing calls without the kwarg must still work. T2
    actually USES the callback; T1 just plumbs the parameter through.
    """
    from backend.server.installer.fabric import FabricInstaller
    import inspect

    sig = inspect.signature(FabricInstaller.install)
    params = sig.parameters
    assert "progress_callback" in params
    assert params["progress_callback"].default is None
