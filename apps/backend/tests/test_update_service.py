"""Tests for the systemd trigger-file self-update flow."""
from __future__ import annotations

import pytest

import backend.system.update_service as update_module
from backend.system.update_service import UpdateService


@pytest.fixture
def svc(tmp_path, monkeypatch):
    """An UpdateService in systemd mode, pointed at a temp control dir."""
    monkeypatch.setenv("FABRICATOR_UPDATE_MODE", "systemd")
    monkeypatch.setenv("FABRICATOR_UPDATE_DIR", str(tmp_path / "update"))
    monkeypatch.setenv("FABRICATOR_REPO", "philderks/Fabricator")
    # No network in tests.
    monkeypatch.setattr(update_module, "_fetch_latest_tag", lambda repo: "v9.9.9")
    return UpdateService()


def _request_file(svc):
    return svc._request_file


def test_idle_before_any_trigger(svc):
    status = svc.get_status()
    assert status["inProgress"] is False
    assert status["lastExitCode"] is None
    assert status["logs"] == []


def test_trigger_writes_request_file(svc):
    result = svc.trigger_update("v1.2.3")
    assert result == {"started": True, "requestedVersion": "v1.2.3"}

    assert _request_file(svc).read_text(encoding="utf-8").strip() == "v1.2.3"
    status = svc.get_status()
    assert status["inProgress"] is True
    assert status["lastRequestedVersion"] == "v1.2.3"


def test_blank_version_defaults_to_latest(svc):
    assert svc.trigger_update(None)["requestedVersion"] == "latest"
    assert _request_file(svc).read_text(encoding="utf-8").strip() == "latest"


@pytest.mark.parametrize("bad", ["; rm -rf /", "a b", "v1$(whoami)", "../etc", "x\ny"])
def test_malformed_version_is_rejected(svc, bad):
    result = svc.trigger_update(bad)
    assert result["started"] is False
    assert not _request_file(svc).exists()


def test_second_trigger_blocked_while_in_progress(svc):
    svc.trigger_update("v1.0.0")
    blocked = svc.trigger_update("v2.0.0")
    assert blocked == {"started": False, "error": "An update is already in progress."}
    # The original request is untouched.
    assert _request_file(svc).read_text(encoding="utf-8").strip() == "v1.0.0"


def test_completion_reports_success(svc):
    svc.trigger_update("v1.0.0")
    # Simulate the oneshot: clears request, writes result + log.
    _request_file(svc).unlink()
    svc._result_file.write_text("0", encoding="utf-8")
    svc._log_file.write_text("starting\ndone\n", encoding="utf-8")

    status = svc.get_status()
    assert status["inProgress"] is False
    assert status["lastExitCode"] == 0
    assert status["lastError"] is None
    assert status["logs"] == ["starting", "done"]


def test_completion_reports_failure(svc):
    svc.trigger_update("v1.0.0")
    _request_file(svc).unlink()
    svc._result_file.write_text("1", encoding="utf-8")

    status = svc.get_status()
    assert status["inProgress"] is False
    assert status["lastExitCode"] == 1
    assert status["lastError"] == "Update failed with exit code 1"


def test_stale_request_is_not_in_progress(svc, monkeypatch):
    svc.trigger_update("v1.0.0")
    # Age the request file well past the staleness window.
    import os

    old = update_module._REQUEST_STALE_AFTER + 120
    st = svc._request_file.stat()
    os.utime(svc._request_file, (st.st_atime - old, st.st_mtime - old))

    assert svc.get_status()["inProgress"] is False


def test_update_available_reflects_version_gap(svc, monkeypatch):
    import backend.core.version as version_module

    monkeypatch.setattr(version_module, "get_app_version", lambda: "v1.0.0")
    assert svc.get_status()["updateAvailable"] is True

    monkeypatch.setattr(version_module, "get_app_version", lambda: "v9.9.9")
    assert svc.get_status()["updateAvailable"] is False
