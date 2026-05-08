"""Fabricator self-update status and execution service."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
import time
from collections import deque
from typing import Any, Dict, Optional
from pathlib import Path
from urllib import error, request
import json

from backend.core.version import get_app_version


_TAG_CACHE_TTL = 15 * 60  # seconds
_tag_cache: Dict[str, Any] = {"tag": None, "fetched_at": 0.0}
_tag_cache_lock = threading.Lock()


def _fetch_latest_tag(repo: str) -> Optional[str]:
    with _tag_cache_lock:
        if time.time() - _tag_cache["fetched_at"] < _TAG_CACHE_TTL:
            return _tag_cache["tag"]

    url = f"https://api.github.com/repos/{repo}/releases/latest"
    req = request.Request(url, headers={"Accept": "application/vnd.github+json"})
    tag: Optional[str] = None
    try:
        with request.urlopen(req, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
            value = payload.get("tag_name")
            if isinstance(value, str) and value:
                tag = value
    except (error.URLError, error.HTTPError, TimeoutError, OSError, json.JSONDecodeError):
        pass

    with _tag_cache_lock:
        _tag_cache["tag"] = tag
        _tag_cache["fetched_at"] = time.time()

    return tag


class UpdateService:
    """In-process update coordinator with execution lock and status snapshots."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._logs: deque[str] = deque(maxlen=500)
        self._in_progress = False
        self._last_started_at: Optional[float] = None
        self._last_finished_at: Optional[float] = None
        self._last_exit_code: Optional[int] = None
        self._last_error: Optional[str] = None
        self._last_triggered_version: Optional[str] = None
        self._repo = os.environ.get("FABRICATOR_REPO", "philderks/Fabricator")

    def _build_update_cmd(self, version: str) -> list[str]:
        """Prefer local tools/update.sh with sudo — matches packaged Linux systemd installs."""

        curl_updater = (
            "curl -fsSL "
            "'https://raw.githubusercontent.com/philderks/Fabricator/main/tools/install.sh' "
            "| bash -s -- --update"
        )

        update_sh = Path(__file__).resolve().parents[2] / "tools" / "update.sh"
        linuxish = sys.platform.startswith("linux")
        sudo_bin = Path("/usr/bin/sudo")

        # Packaged installs run as an unprivileged user and must elevate to run install.sh.
        if linuxish and update_sh.is_file():
            bash_bin = Path(shutil.which("bash") or "/bin/bash").resolve()
            if os.geteuid() == 0:
                return [str(bash_bin), str(update_sh), version]
            if sudo_bin.is_file():
                return [
                    str(sudo_bin),
                    "-n",
                    str(bash_bin),
                    str(update_sh),
                    version,
                ]

        # Dev installs / non-Linux fallback (requires sufficient privileges for the installer).
        return ["/usr/bin/env", "bash", "-lc", curl_updater]

    def _run_update(self, version: str) -> None:
        env = os.environ.copy()
        env["FABRICATOR_VERSION"] = version
        cmd = self._build_update_cmd(version)

        with self._state_lock:
            self._in_progress = True
            self._last_started_at = time.time()
            self._last_finished_at = None
            self._last_exit_code = None
            self._last_error = None
            self._last_triggered_version = version
            self._logs.clear()
            self._logs.append(f"Starting update (target: {version})")

        try:
            completed = subprocess.run(  # noqa: S603
                cmd,
                capture_output=True,
                text=True,
                env=env,
                check=False,
            )
            output = (completed.stdout or "").strip()
            errors = (completed.stderr or "").strip()
            with self._state_lock:
                if output:
                    self._logs.extend(output.splitlines())
                if errors:
                    self._logs.extend(errors.splitlines())
                self._last_exit_code = completed.returncode
                if completed.returncode != 0 and not self._last_error:
                    self._last_error = f"Update failed with exit code {completed.returncode}"
        except OSError as exc:
            with self._state_lock:
                self._last_error = f"Failed to execute updater: {exc}"
                self._last_exit_code = 1
                self._logs.append(self._last_error)
        finally:
            with self._state_lock:
                self._in_progress = False
                self._last_finished_at = time.time()

    def get_status(self) -> Dict[str, Any]:
        current_version = get_app_version()
        latest = _fetch_latest_tag(self._repo)
        with self._state_lock:
            return {
                "inProgress": self._in_progress,
                "currentVersion": current_version,
                "latestVersion": latest,
                "updateAvailable": bool(latest and latest != current_version),
                "lastStartedAt": self._last_started_at,
                "lastFinishedAt": self._last_finished_at,
                "lastExitCode": self._last_exit_code,
                "lastError": self._last_error,
                "lastRequestedVersion": self._last_triggered_version,
                "logs": list(self._logs),
                "updaterScript": "https://raw.githubusercontent.com/philderks/Fabricator/main/tools/install.sh",
            }

    def trigger_update(self, version: Optional[str] = None) -> Dict[str, Any]:
        requested_version = (version or "latest").strip() or "latest"
        if self._in_progress:
            return {
                "started": False,
                "error": "An update is already in progress.",
            }

        if not self._lock.acquire(blocking=False):
            return {
                "started": False,
                "error": "Updater lock is currently held.",
            }

        def _runner() -> None:
            try:
                self._run_update(requested_version)
            finally:
                self._lock.release()

        threading.Thread(target=_runner, daemon=True).start()
        return {
            "started": True,
            "requestedVersion": requested_version,
        }


update_service = UpdateService()
