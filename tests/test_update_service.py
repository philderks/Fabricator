"""Tests for the self-update flows (systemd trigger-file and Windows exe)."""
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


# --------------------------------------------------------------------------- #
# Windows exe mode                                                            #
# --------------------------------------------------------------------------- #
import hashlib
import io
import json
import sys
import threading


@pytest.fixture
def exe_svc(tmp_path, monkeypatch):
    monkeypatch.setenv("FABRICATOR_UPDATE_MODE", "exe")
    monkeypatch.delenv("FABRICATOR_UPDATE_RESULT", raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "Fabricator.exe"))
    monkeypatch.setattr(update_module, "_fetch_latest_tag", lambda repo: "v2.0.0")
    svc = UpdateService()
    svc.shutdown_calls = []
    svc.shutdown = lambda: svc.shutdown_calls.append(True)
    return svc


def _serve_release(monkeypatch, payload: bytes, digest: str):
    meta = json.dumps({"assets": [{
        "name": "Fabricator-v2.0.0.exe",
        "digest": digest,
        "browser_download_url": "https://github.com/x/Fabricator-v2.0.0.exe",
    }]}).encode()

    def urlopen(req, timeout=None):
        return io.BytesIO(meta if isinstance(req, update_module.request.Request) else payload)

    monkeypatch.setattr(update_module.request, "urlopen", urlopen)


def test_exe_download_verifies_sha256(tmp_path, monkeypatch):
    payload = b"MZ new build"
    _serve_release(monkeypatch, payload, "sha256:" + hashlib.sha256(payload).hexdigest())
    dest = tmp_path / "Fabricator.exe.new"
    update_module._download_release_exe("r", "v2.0.0", dest)
    assert dest.read_bytes() == payload


@pytest.mark.parametrize("digest", ["sha256:" + "0" * 64, "", "md5:abc"])
def test_exe_download_rejects_unverifiable_build(tmp_path, monkeypatch, digest):
    _serve_release(monkeypatch, b"MZ tampered", digest)
    dest = tmp_path / "Fabricator.exe.new"
    with pytest.raises(RuntimeError):
        update_module._download_release_exe("r", "v2.0.0", dest)
    assert not dest.exists()


def test_exe_update_starts_swap_helper_then_shuts_down(exe_svc, monkeypatch, tmp_path):
    payload = b"MZ new build"
    _serve_release(monkeypatch, payload, "sha256:" + hashlib.sha256(payload).hexdigest())
    spawned = []
    monkeypatch.setattr(
        update_module.subprocess, "Popen",
        lambda args, **kw: spawned.append((args, kw["env"], len(exe_svc.shutdown_calls))),
    )

    exe_svc._run_update_exe("latest")

    (args, env, shutdowns_before_spawn), = spawned
    assert args[0] == "powershell"
    assert env["FAB_NEW"] == str(tmp_path / "Fabricator.exe.new")
    assert env["FAB_EXE"] == str(tmp_path / "Fabricator.exe")
    assert env["PYINSTALLER_RESET_ENVIRONMENT"] == "1"
    assert (tmp_path / "Fabricator.exe.new").read_bytes() == payload
    assert shutdowns_before_spawn == 0 and exe_svc.shutdown_calls == [True]


def test_exe_update_failure_keeps_panel_running(exe_svc, monkeypatch):
    _serve_release(monkeypatch, b"MZ tampered", "sha256:" + "0" * 64)
    monkeypatch.setattr(update_module.subprocess, "Popen", lambda *a, **k: pytest.fail("spawned"))

    exe_svc._run_update_exe("v2.0.0")

    status = exe_svc.get_status()
    assert exe_svc.shutdown_calls == []
    assert status["inProgress"] is False
    assert status["lastExitCode"] == 1
    assert "checksum" in status["lastError"]


def test_trigger_reports_in_progress_before_runner_starts(exe_svc, monkeypatch):
    release = threading.Event()
    monkeypatch.setattr(exe_svc, "_run_update_exe", lambda version: release.wait(5))
    assert exe_svc.trigger_update("v2.0.0")["started"] is True
    assert exe_svc.get_status()["inProgress"] is True
    release.set()


@pytest.mark.parametrize("result, code", [("0", 0), ("1", 1)])
def test_relaunched_process_reports_swap_result(monkeypatch, result, code):
    monkeypatch.setenv("FABRICATOR_UPDATE_MODE", "exe")
    monkeypatch.setenv("FABRICATOR_UPDATE_RESULT", result)
    monkeypatch.setattr(update_module, "_fetch_latest_tag", lambda repo: "v2.0.0")
    status = UpdateService().get_status()
    assert status["inProgress"] is False
    assert status["lastExitCode"] == code
    assert (status["lastError"] is None) == (code == 0)


def test_latest_tag_skips_mcp_and_prereleases(monkeypatch):
    releases = [
        {"tag_name": "mcp-v0.2.0"},
        {"tag_name": "v2.0.0-beta", "prerelease": True},
        {"tag_name": "v1.9.0", "draft": True},
        {"tag_name": "v1.8.0"},
    ]
    monkeypatch.setitem(update_module._tag_cache, "tag", None)
    monkeypatch.setitem(update_module._tag_cache, "fetched_at", 0.0)
    monkeypatch.setattr(
        update_module.request, "urlopen",
        lambda req, timeout=None: io.BytesIO(json.dumps(releases).encode()),
    )
    assert update_module._fetch_latest_tag("r") == "v1.8.0"
