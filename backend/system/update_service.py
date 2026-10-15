"""Fabricator self-update status and execution service.

Three execution modes:

* ``systemd`` (packaged Linux installs): the panel runs as an unprivileged,
  heavily-sandboxed systemd service (``NoNewPrivileges=true``,
  ``ProtectSystem=strict``). It cannot ``sudo`` to run the installer, so it
  instead drops a *request file* into its writable state dir. A root-owned
  ``fabricator-update.path`` unit watches that file and starts the
  ``fabricator-update.service`` oneshot — outside the panel's sandbox, and
  decoupled from it so the installer's restart of the panel does not kill the
  update mid-flight. Status/logs are read back from files the oneshot writes.

* ``exe`` (the portable Windows build, picked automatically when frozen on
  Windows): download the release ``.exe`` next to the running one, verify it
  against GitHub's sha256, and hand off to a detached PowerShell helper that
  swaps it in once this process has exited and relaunches it.

* ``dev`` (everything else): fall back to running the installer in-process via
  ``curl | bash``. Requires the caller to already have sufficient privileges.
"""
from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys
import threading
import time
from collections import deque
from typing import Any, Callable, Dict, Optional
from pathlib import Path
from urllib import error, request
import json


_TAG_CACHE_TTL = 15 * 60  # seconds
_tag_cache: Dict[str, Any] = {"tag": None, "fetched_at": 0.0}
_tag_cache_lock = threading.Lock()

# A pinned version is only ever a release tag or the literal "latest". Anything
# else is rejected so a (potentially compromised) unprivileged panel cannot use
# the request file as an injection vector into the root oneshot.
_VERSION_RE = re.compile(r"^[A-Za-z0-9._-]+$")

# Treat a lingering request file as stale after this long so a path unit that
# never fired (misconfigured host) does not wedge the UI in "Updating…".
_REQUEST_STALE_AFTER = 60 * 60  # seconds

# Runs detached after the panel exits. The exe stays locked until both
# PyInstaller onefile processes (bootloader + app) are gone, which includes the
# graceful server stop, so the move is retried. Whichever exe ends up in place
# is started, so a failed swap still brings the panel back on the old version;
# FABRICATOR_UPDATE_RESULT tells the relaunched process which one happened.
_EXE_SWAP_SCRIPT = (
    "$env:FABRICATOR_UPDATE_RESULT = '1';"
    " for ($i = 0; $i -lt 300; $i++) {"
    " try { Move-Item -LiteralPath $env:FAB_NEW -Destination $env:FAB_EXE -Force -ErrorAction Stop;"
    " $env:FABRICATOR_UPDATE_RESULT = '0'; break }"
    " catch { Start-Sleep -Seconds 1 } };"
    " Start-Process -FilePath $env:FAB_EXE"
)


def _fetch_latest_tag(repo: str) -> Optional[str]:
    with _tag_cache_lock:
        if time.time() - _tag_cache["fetched_at"] < _TAG_CACHE_TTL:
            return _tag_cache["tag"]

    # Same filter as install.sh's get_latest_tag: GitHub's /releases/latest can
    # be an mcp-v* release, which has no panel assets.
    url = f"https://api.github.com/repos/{repo}/releases?per_page=100"
    req = request.Request(url, headers={"Accept": "application/vnd.github+json"})
    tag: Optional[str] = None
    try:
        with request.urlopen(req, timeout=10) as response:
            releases = json.loads(response.read().decode("utf-8"))
        tag = next((
            r["tag_name"] for r in releases
            if isinstance(r, dict) and isinstance(r.get("tag_name"), str)
            and r["tag_name"].startswith("v")
            and not r.get("draft") and not r.get("prerelease")
        ), None)
    except (error.URLError, error.HTTPError, TimeoutError, OSError, ValueError, TypeError):
        pass

    with _tag_cache_lock:
        _tag_cache["tag"] = tag
        _tag_cache["fetched_at"] = time.time()

    return tag


def _download_release_exe(repo: str, tag: str, dest: Path) -> None:
    """Download ``Fabricator-<tag>.exe`` to ``dest``, verified against GitHub's sha256."""
    meta = request.Request(
        f"https://api.github.com/repos/{repo}/releases/tags/{tag}",
        headers={"Accept": "application/vnd.github+json"},
    )
    with request.urlopen(meta, timeout=15) as response:
        assets = json.loads(response.read().decode("utf-8")).get("assets") or []
    name = f"Fabricator-{tag}.exe"
    asset = next((a for a in assets if a.get("name") == name), None)
    if asset is None:
        raise RuntimeError(f"Release {tag} has no {name}.")
    algo, _, expected = str(asset.get("digest") or "").partition(":")
    if algo != "sha256" or not expected:
        raise RuntimeError(f"{name} has no sha256 digest to verify against.")

    sha = hashlib.sha256()
    try:
        with request.urlopen(asset["browser_download_url"], timeout=30) as response, \
                dest.open("wb") as fh:
            for chunk in iter(lambda: response.read(1 << 16), b""):
                sha.update(chunk)
                fh.write(chunk)
        if sha.hexdigest() != expected:
            raise RuntimeError(f"{name} failed checksum verification.")
    except Exception:
        dest.unlink(missing_ok=True)
        raise


def _normalize_version(version: Optional[str]) -> Optional[str]:
    """Return a validated version string, or ``None`` if it is malformed."""
    candidate = (version or "latest").strip() or "latest"
    if not _VERSION_RE.match(candidate):
        return None
    return candidate


class UpdateService:
    """Update coordinator. Picks systemd trigger-file, Windows exe, or dev mode."""

    def __init__(self) -> None:
        self._state_lock = threading.Lock()
        self._repo = os.environ.get("FABRICATOR_REPO", "philderks/Fabricator")

        self._mode = os.environ.get("FABRICATOR_UPDATE_MODE", "").strip().lower()
        if not self._mode and getattr(sys, "frozen", False) and sys.platform == "win32":
            self._mode = "exe"
        # run.py installs its graceful shutdown here; the exe updater exits
        # through it so running servers save their worlds before the swap.
        self.shutdown: Optional[Callable[[], None]] = None
        update_dir = os.environ.get(
            "FABRICATOR_UPDATE_DIR", "/var/lib/fabricator/update"
        )
        self._update_dir = Path(update_dir)
        self._request_file = self._update_dir / "request"
        self._log_file = self._update_dir / "update.log"
        self._result_file = self._update_dir / "result"

        # In-process (dev) execution bookkeeping.
        self._lock = threading.Lock()
        self._logs: deque[str] = deque(maxlen=500)
        self._in_progress = False
        self._last_started_at: Optional[float] = None
        self._last_finished_at: Optional[float] = None
        self._last_exit_code: Optional[int] = None
        self._last_error: Optional[str] = None
        self._last_triggered_version: Optional[str] = None

        # Set by the exe swap helper on the relaunched process, so a UI that
        # polled through the restart learns how the update ended.
        swap_result = os.environ.get("FABRICATOR_UPDATE_RESULT")
        if swap_result is not None:
            self._last_finished_at = time.time()
            self._last_exit_code = 0 if swap_result == "0" else 1
            if self._last_exit_code:
                self._last_error = (
                    "Could not replace the executable; still running the previous version."
                )

    # ------------------------------------------------------------------ #
    # Status                                                             #
    # ------------------------------------------------------------------ #
    def get_status(self) -> Dict[str, Any]:
        # Imported lazily: a module-level import would pull in backend.core →
        # app → system.routes → back here, a cycle when update_service is the
        # first module imported (e.g. in isolated tests).
        from backend.core.version import get_app_version

        current_version = get_app_version()
        latest = _fetch_latest_tag(self._repo)
        if self._mode == "systemd":
            state = self._systemd_state()
        else:
            with self._state_lock:
                state = {
                    "inProgress": self._in_progress,
                    "lastStartedAt": self._last_started_at,
                    "lastFinishedAt": self._last_finished_at,
                    "lastExitCode": self._last_exit_code,
                    "lastError": self._last_error,
                    "lastRequestedVersion": self._last_triggered_version,
                    "logs": list(self._logs),
                }
        return {
            "currentVersion": current_version,
            "latestVersion": latest,
            "updateAvailable": bool(latest and latest != current_version),
            "updaterScript": "https://raw.githubusercontent.com/philderks/Fabricator/main/tools/install.sh",
            **state,
        }

    def _systemd_state(self) -> Dict[str, Any]:
        """Reconstruct update state from the files the oneshot unit writes."""
        request_exists = self._request_file.is_file()
        request_mtime = self._file_mtime(self._request_file)
        result_mtime = self._file_mtime(self._result_file)

        # The oneshot removes the request file in ExecStopPost, so its presence
        # means a job is queued or running. Guard against a path unit that never
        # fired by ageing the request out.
        in_progress = request_exists
        if request_exists and request_mtime is not None:
            if time.time() - request_mtime > _REQUEST_STALE_AFTER:
                in_progress = False

        exit_code = self._read_result()
        last_error: Optional[str] = None
        if not in_progress and exit_code not in (None, 0):
            last_error = f"Update failed with exit code {exit_code}"

        return {
            "inProgress": in_progress,
            "lastStartedAt": request_mtime,
            "lastFinishedAt": None if in_progress else result_mtime,
            "lastExitCode": None if in_progress else exit_code,
            "lastError": last_error,
            "lastRequestedVersion": self._read_request_version(),
            "logs": self._read_logs(),
        }

    # ------------------------------------------------------------------ #
    # Trigger                                                            #
    # ------------------------------------------------------------------ #
    def trigger_update(self, version: Optional[str] = None) -> Dict[str, Any]:
        normalized = _normalize_version(version)
        if normalized is None:
            return {
                "started": False,
                "error": "Invalid version. Use a release tag or 'latest'.",
            }

        if self._mode == "systemd":
            return self._trigger_systemd(normalized)
        return self._trigger_dev(normalized)

    def _trigger_systemd(self, version: str) -> Dict[str, Any]:
        state = self._systemd_state()
        if state["inProgress"]:
            return {"started": False, "error": "An update is already in progress."}

        try:
            self._update_dir.mkdir(parents=True, exist_ok=True)
            # Atomic publish: the path unit watches `request`, so it must only
            # ever observe a complete file.
            tmp = self._request_file.with_suffix(".tmp")
            tmp.write_text(version + "\n", encoding="utf-8")
            os.replace(tmp, self._request_file)
        except OSError as exc:
            return {
                "started": False,
                "error": f"Failed to queue update request: {exc}",
            }

        return {"started": True, "requestedVersion": version}

    # ------------------------------------------------------------------ #
    # Dev (in-process) execution                                         #
    # ------------------------------------------------------------------ #
    def _trigger_dev(self, version: str) -> Dict[str, Any]:
        if self._in_progress:
            return {"started": False, "error": "An update is already in progress."}
        if not self._lock.acquire(blocking=False):
            return {"started": False, "error": "Updater lock is currently held."}

        with self._state_lock:
            self._in_progress = True
            self._last_started_at = time.time()
            self._last_finished_at = None
            self._last_exit_code = None
            self._last_error = None
            self._last_triggered_version = version
            self._logs.clear()
            self._logs.append(f"Starting update (target: {version})")

        run = self._run_update_exe if self._mode == "exe" else self._run_update_dev

        def _runner() -> None:
            try:
                run(version)
            finally:
                self._lock.release()

        threading.Thread(target=_runner, daemon=True).start()
        return {"started": True, "requestedVersion": version}

    def _run_update_dev(self, version: str) -> None:
        curl_updater = (
            "curl -fsSL "
            "'https://raw.githubusercontent.com/philderks/Fabricator/main/tools/install.sh' "
            "| bash -s -- --update"
        )
        cmd = ["/usr/bin/env", "bash", "-lc", curl_updater]
        env = os.environ.copy()
        env["FABRICATOR_VERSION"] = version

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

    def _run_update_exe(self, version: str) -> None:
        # A running exe can't be overwritten, so download beside it and let the
        # swap helper move it into place after we exit.
        try:
            if self.shutdown is None:
                raise RuntimeError("No shutdown hook installed; cannot restart.")
            tag = _fetch_latest_tag(self._repo) if version == "latest" else version
            if not tag:
                raise RuntimeError("Could not determine the latest release.")
            exe = Path(sys.executable)
            new_exe = exe.with_name(exe.name + ".new")
            with self._state_lock:
                self._logs.append(f"Downloading Fabricator-{tag}.exe")
            _download_release_exe(self._repo, tag, new_exe)
            env = {
                **os.environ,
                "FAB_NEW": str(new_exe),
                "FAB_EXE": str(exe),
                # Relaunch as an independent instance, not a worker reusing
                # this process's onefile temp dir (deleted when we exit).
                "PYINSTALLER_RESET_ENVIRONMENT": "1",
            }
            subprocess.Popen(  # noqa: S603
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", _EXE_SWAP_SCRIPT],
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
                | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
            )
        except Exception as exc:
            with self._state_lock:
                self._last_error = f"Update failed: {exc}"
                self._last_exit_code = 1
                self._logs.append(self._last_error)
                self._in_progress = False
                self._last_finished_at = time.time()
            return
        with self._state_lock:
            self._logs.append("Download verified; restarting into the new version")
        self.shutdown()

    # ------------------------------------------------------------------ #
    # File helpers (systemd mode)                                        #
    # ------------------------------------------------------------------ #
    @staticmethod
    def _file_mtime(path: Path) -> Optional[float]:
        try:
            return path.stat().st_mtime
        except OSError:
            return None

    def _read_request_version(self) -> Optional[str]:
        try:
            value = self._request_file.read_text(encoding="utf-8").strip()
        except OSError:
            return None
        return value or None

    def _read_result(self) -> Optional[int]:
        try:
            raw = self._result_file.read_text(encoding="utf-8").strip()
        except OSError:
            return None
        try:
            return int(raw)
        except ValueError:
            # systemd writes a signal name (e.g. "TERM") for killed jobs.
            return 1 if raw else None

    def _read_logs(self) -> list[str]:
        try:
            with self._log_file.open("r", encoding="utf-8", errors="replace") as fh:
                tail = deque(fh, maxlen=500)
        except OSError:
            return []
        return [line.rstrip("\n") for line in tail]


update_service = UpdateService()
