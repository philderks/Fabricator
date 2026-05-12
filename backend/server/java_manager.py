"""Managed Java runtime download, install and resolution.

Single source of truth for locating a JDK that is compatible with a given
Minecraft server. Falls back to downloading the Temurin (Adoptium) build when
no suitable system Java is available. Installs are performed entirely under
Fabricator's own data directory so no elevated permissions are required.
"""
from __future__ import annotations

import hashlib
import logging
import os
import shutil
import subprocess
import tarfile
import threading
import time
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

import requests

from backend.core.config import get_config
from backend.server.installer.base import request_with_retry
from backend.server.java_compat import resolve_required_java
from backend.utils import platform as platform_utils
from backend.utils.java import parse_java_major
from backend.utils.zip import safe_extract_zip


logger = logging.getLogger(__name__)


ADOPTIUM_API = "https://api.adoptium.net/v3/assets/latest/{major}/hotspot"

# How long ``java -version`` is allowed to run before we treat the system Java
# as unreachable. NFS mounts, AV scans on a freshly-extracted JDK, or a stale
# binary on a path that no longer resolves can otherwise hang the request
# thread indefinitely (B13: subprocess.run had no timeout pre-fix).
_SYSTEM_JAVA_VERSION_TIMEOUT_SEC = 10

# Retention window for completed install tasks. After a task transitions to
# ``done`` / ``error`` it stays addressable for this long so the frontend can
# poll for the final state, then is evicted on the next bookkeeping pass.
# Active (queued / downloading / installing) tasks are NEVER evicted.
_INSTALL_TASK_RETENTION_SEC = 3600  # 1 hour

# Wall-clock cap for a single install task. ``threading.Thread`` cannot be
# hard-killed in Python, so this is a best-effort signal: a watchdog flips the
# task to ``error`` once exceeded and sets ``cancel_event``, which the install
# routine checks between phases. An in-flight ``requests.get`` is already
# bounded by its own per-request ``timeout=`` so the worst-case hang is
# bounded by that, not by the wall-clock cap.
_INSTALL_TASK_MAX_RUNTIME_SEC = 30 * 60  # 30 minutes

# Number of additional retries for transient Adoptium failures (5xx / 408 /
# 429 / ConnectionError / Timeout). Matches the convention used by the loader
# installers via ``request_with_retry`` (B12b).
_ADOPTIUM_RETRIES = 3

# Adoptium does not publish Java 16 binaries. Minecraft 1.17.x runs fine on
# Java 17, so we substitute transparently.
_MAJOR_FALLBACKS: dict[int, int] = {16: 17}


def required_java_for(mc_version: str) -> int:
    """Return the minimum Java major version required for an MC version string.

    Delegates to :func:`resolve_required_java`. Defaults to Java 21 when the
    version string is empty or unrecognised (e.g. snapshot strings like
    ``"24w14a"``) to match modern vanilla defaults.
    """
    compat = resolve_required_java(mc_version or "")
    if compat.required_java is None:
        return 21
    return int(compat.required_java)


def effective_install_major(required: int) -> int:
    """Map a required Java major to one that is actually installable.

    Adoptium does not ship Java 16, so callers that need Java 16 transparently
    get Java 17 which is backwards compatible for Minecraft 1.17.x.
    """
    return _MAJOR_FALLBACKS.get(int(required), int(required))


def _adoptium_os_label() -> str:
    label = platform_utils.platform_label()
    if label == "darwin":
        return "mac"
    return label  # linux / windows


def _is_windows() -> bool:
    return platform_utils.is_windows()


def java_binary(major: int) -> str:
    """Return the OS-specific java executable filename."""
    _ = major  # reserved for future per-major differences
    return "java.exe" if _is_windows() else "java"


def _managed_base() -> Path:
    """Return the base directory that holds all managed JDK trees.

    Resolution order: ``JAVA_ROOT`` env var (via Config) → Config default
    (which is ``%APPDATA%\\Fabricator\\java`` on Windows, project-relative
    elsewhere). All Windows path handling lives in Config so env vars work
    consistently across platforms.
    """
    config = get_config()
    configured = getattr(config, "JAVA_ROOT", None)
    if configured:
        return Path(configured).expanduser()
    return Path(config.PROJECT_ROOT) / "java"


def managed_java_dir(major: int) -> Path:
    """Return the managed install directory for the given Java major version."""
    return _managed_base() / str(int(major))


def managed_java_binary_path(major: int) -> Path:
    """Full path to java[.exe] inside the managed install for ``major``."""
    return managed_java_dir(major) / "bin" / java_binary(major)


def _parse_system_java_major() -> Optional[int]:
    """Invoke ``java -version`` and return the detected major, or None.

    A ``timeout=_SYSTEM_JAVA_VERSION_TIMEOUT_SEC`` guard prevents the call
    from hanging the request thread when the system ``java`` is on a stale
    NFS mount, mid-AV-scan, or otherwise wedged. ``TimeoutExpired`` (and
    other ``OSError`` flavours) are treated identically to a missing binary:
    return ``None`` and let the caller fall back to a managed install.
    """
    try:
        result = subprocess.run(
            ["java", "-version"],
            capture_output=True,
            text=True,
            timeout=_SYSTEM_JAVA_VERSION_TIMEOUT_SEC,
            **platform_utils.subprocess_no_window_kwargs(),
        )
    except FileNotFoundError:
        return None
    except subprocess.TimeoutExpired:
        logger.warning(
            "system 'java -version' timed out after %ds; treating as no system java",
            _SYSTEM_JAVA_VERSION_TIMEOUT_SEC,
        )
        return None
    except OSError as exc:
        logger.warning("system 'java -version' failed: %s", exc)
        return None
    output = (result.stdout or "") + (result.stderr or "")
    if result.returncode != 0:
        return None
    return parse_java_major(output)


def find_compatible_java(required: int) -> Optional[str]:
    """Locate a java binary with major >= ``required``.

    Resolution order:
    1. System java on PATH (if ``java -version`` reports a high enough major).
    2. Previously installed managed JDK at the requested major.
    3. Managed JDK at the fallback major (e.g. 17 when 16 was requested).
    4. None — caller must trigger a download.
    """
    required_int = int(required)
    system_major = _parse_system_java_major()
    if system_major is not None and system_major >= required_int:
        return "java"

    managed_path = managed_java_binary_path(required_int)
    if managed_path.exists():
        return str(managed_path)

    install_major = effective_install_major(required_int)
    if install_major != required_int:
        fallback_path = managed_java_binary_path(install_major)
        if fallback_path.exists():
            return str(fallback_path)

    return None


def system_java_info() -> dict:
    """Return a summary of the PATH ``java`` executable for /api/java/status."""
    major = _parse_system_java_major()
    installed = major is not None
    return {
        "path": "java",
        "version": major,
        "installed": installed,
    }


def managed_java_info(major: int) -> dict:
    """Return a summary of the managed install for ``major``."""
    resolved_major = effective_install_major(major)
    path = managed_java_binary_path(resolved_major)
    return {
        "path": str(path),
        "installed": path.exists(),
        "major": resolved_major,
        "requested_major": int(major),
        "substituted": resolved_major != int(major),
    }


def adoptium_asset_url(major: int) -> dict:
    """Return Temurin asset metadata for the current platform + architecture.

    Raises ``RuntimeError`` when the API is unreachable or no asset matches.
    The returned dict has ``download_url``, ``filename``, ``size_bytes``,
    ``checksum`` and ``checksum_algorithm`` keys.

    Transient Adoptium failures (5xx / 408 / 429 / ConnectionError / Timeout)
    are retried with exponential backoff via :func:`request_with_retry`
    (B12b) so a single network hiccup during a JDK install does not force the
    user back to the start of the flow.
    """
    install_major = effective_install_major(major)
    url = ADOPTIUM_API.format(major=install_major)

    def _fetch_assets() -> list:
        response = requests.get(url, timeout=30)
        # ``raise_for_status`` is the trigger that ``request_with_retry`` keys
        # off — without it a 503 / 504 would short-circuit to the "not 200"
        # branch below and never get retried.
        response.raise_for_status()
        try:
            return response.json()
        except ValueError as exc:
            raise RuntimeError(
                f"Adoptium API returned invalid JSON for Java {install_major}"
            ) from exc

    try:
        assets = request_with_retry(
            _fetch_assets,
            retries=_ADOPTIUM_RETRIES,
            on_retry=lambda attempt, exc: logger.warning(
                "Adoptium API retry %d for Java %d: %s", attempt, install_major, exc
            ),
        )
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else "?"
        raise RuntimeError(
            f"Adoptium API returned HTTP {status} for Java {install_major}"
        ) from exc
    except requests.RequestException as exc:
        raise RuntimeError(
            f"Failed to reach Adoptium API for Java {install_major}: {exc}"
        ) from exc

    target_os = _adoptium_os_label()
    target_arch = platform_utils.arch_label()

    for asset in assets:
        binary = asset.get("binary") or {}
        if binary.get("image_type") != "jdk":
            continue
        if binary.get("os") != target_os:
            continue
        if binary.get("architecture") != target_arch:
            continue
        package = binary.get("package") or {}
        link = package.get("link")
        name = package.get("name")
        if not link or not name:
            continue
        return {
            "download_url": link,
            "filename": name,
            "size_bytes": int(package.get("size") or 0),
            "checksum": package.get("checksum"),
            "checksum_algorithm": "sha256",
            "requested_major": int(major),
            "install_major": install_major,
            "substituted": install_major != int(major),
        }

    raise RuntimeError(
        f"No Adoptium JDK asset found for Java {install_major} "
        f"({target_os}/{target_arch})."
    )


def _download_root() -> Path:
    return platform_utils.temp_directory("fabricator-java")


def download_java(
    major: int,
    progress_callback: Optional[Callable[[int, int], None]] = None,
    cancel_event: Optional[threading.Event] = None,
) -> Path:
    """Download the Temurin JDK archive for ``major`` to a temp file.

    Verifies the SHA-256 checksum against the Adoptium API. Returns the path
    to the downloaded archive (not yet extracted). Raises ``RuntimeError`` on
    any network, IO or integrity failure.

    Transient network failures (5xx / 408 / 429 / ConnectionError / Timeout)
    are retried with exponential backoff via :func:`request_with_retry`
    (B12b). Each retry starts the stream from scratch — the per-attempt
    partial file is unlinked before re-entry so a mid-stream socket reset
    cannot leave a half-finished archive behind. A SHA-256 mismatch is
    treated as a hard failure (cryptographic mismatch is by definition
    non-transient) and re-raised without retry.

    ``cancel_event`` (optional): if set during the stream, the download is
    aborted promptly between chunks and the partial file is unlinked.
    Used by the background-task watchdog to enforce
    ``_INSTALL_TASK_MAX_RUNTIME_SEC`` between phases.
    """
    asset = adoptium_asset_url(major)
    download_dir = _download_root()
    target = download_dir / asset["filename"]

    expected = (asset.get("checksum") or "").lower()

    def _attempt() -> Path:
        if cancel_event is not None and cancel_event.is_set():
            raise RuntimeError("Java install was cancelled")

        hasher = hashlib.sha256()
        total = asset["size_bytes"] or 0
        downloaded = 0
        # Partial bytes from a prior failed attempt would corrupt the hash
        # of the next attempt — start each retry from a clean slate.
        _safe_unlink(target)

        try:
            with requests.get(asset["download_url"], stream=True, timeout=60) as response:
                response.raise_for_status()
                content_length = response.headers.get("Content-Length")
                if not total and content_length and content_length.isdigit():
                    total = int(content_length)
                if progress_callback:
                    progress_callback(0, total)
                with open(target, "wb") as fh:
                    for chunk in response.iter_content(chunk_size=1024 * 256):
                        if cancel_event is not None and cancel_event.is_set():
                            raise RuntimeError("Java install was cancelled")
                        if not chunk:
                            continue
                        fh.write(chunk)
                        hasher.update(chunk)
                        downloaded += len(chunk)
                        if progress_callback:
                            progress_callback(downloaded, total or downloaded)
        except BaseException:
            # Any failure path leaves a partial archive on disk; unlink it
            # so the next attempt (retry or caller-driven retry) starts from
            # a clean slate. ``BaseException`` (not ``Exception``) covers
            # cancellation flavours that subclass it.
            _safe_unlink(target)
            raise

        actual = hasher.hexdigest()
        if expected and expected != actual:
            _safe_unlink(target)
            # Raised outside the ``requests.RequestException`` branch so
            # ``request_with_retry`` does not retry on integrity failure.
            raise RuntimeError(
                "Java archive checksum mismatch: expected "
                f"{expected[:12]}..., got {actual[:12]}..."
            )

        return target

    try:
        return request_with_retry(
            _attempt,
            retries=_ADOPTIUM_RETRIES,
            on_retry=lambda attempt, exc: logger.warning(
                "Adoptium download retry %d for Java %d: %s",
                attempt, major, exc,
            ),
        )
    except requests.RequestException as exc:
        raise RuntimeError(f"Failed downloading Java archive: {exc}") from exc


def _safe_unlink(path: Path) -> None:
    try:
        if path.exists():
            path.unlink()
    except OSError:
        pass


def _safe_rmtree(path: Path) -> None:
    try:
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)
    except OSError:
        pass


def _find_single_top_level(root: Path) -> Path:
    """Return the single top-level entry of an extracted Temurin archive.

    Temurin archives always contain exactly one directory like
    ``jdk-21.0.3+9/`` at the root. Raises ``RuntimeError`` if the archive
    does not follow this shape.
    """
    entries = [child for child in root.iterdir() if not child.name.startswith(".")]
    if len(entries) == 1 and entries[0].is_dir():
        return entries[0]
    raise RuntimeError(
        f"Unexpected Temurin archive layout: {[c.name for c in entries]}"
    )


def _extract_archive(archive: Path, staging: Path) -> None:
    if archive.suffixes[-2:] == [".tar", ".gz"] or archive.suffix == ".tgz":
        with tarfile.open(archive, "r:gz") as tar:
            _safe_extract_tar(tar, staging)
    elif archive.suffix == ".zip":
        with zipfile.ZipFile(archive, "r") as zf:
            safe_extract_zip(zf, staging)
    else:
        raise RuntimeError(f"Unsupported archive format: {archive.name}")


def _safe_extract_tar(tar: tarfile.TarFile, destination: Path) -> None:
    destination = destination.resolve()
    for member in tar.getmembers():
        member_path = (destination / member.name).resolve()
        if not str(member_path).startswith(str(destination)):
            raise RuntimeError("Archive contains invalid paths")
    tar.extractall(destination)


def install_java(major: int, archive_path: Path) -> str:
    """Extract ``archive_path`` into :func:`managed_java_dir` for ``major``.

    Flattens the single Temurin top-level directory so that the final layout
    is ``managed_java_dir/bin/java[.exe]``. Any existing install for this
    major is replaced. Cleans up the archive and staging dir on the way out.
    Returns the absolute path of the java binary.
    """
    install_major = effective_install_major(major)
    target_dir = managed_java_dir(install_major)
    target_dir.parent.mkdir(parents=True, exist_ok=True)

    staging = _download_root() / f"stage-{install_major}-{uuid.uuid4().hex}"
    staging.mkdir(parents=True, exist_ok=True)

    try:
        _extract_archive(archive_path, staging)
        top = _find_single_top_level(staging)

        if target_dir.exists():
            _safe_rmtree(target_dir)
        target_dir.mkdir(parents=True, exist_ok=True)

        for child in top.iterdir():
            shutil.move(str(child), str(target_dir / child.name))
    finally:
        _safe_rmtree(staging)
        _safe_unlink(archive_path)

    binary_path = managed_java_binary_path(install_major)
    if not binary_path.exists():
        raise RuntimeError(
            f"Java install completed but binary not found at {binary_path}"
        )

    try:
        os.chmod(binary_path, 0o755)
    except OSError:
        pass

    return str(binary_path)


# ---------------------------------------------------------------------------
# Background install tasks (polling API)
# ---------------------------------------------------------------------------


_install_tasks_lock = threading.Lock()
_install_tasks: dict[str, dict] = {}

# Internal handles per task — kept out of ``_install_tasks`` so the dict that
# escapes via :func:`get_install_task` stays JSON-serialisable. Keys mirror
# ``_install_tasks``; entries are removed by :func:`_evict_old_install_tasks`.
_install_task_handles: dict[str, dict] = {}

_TERMINAL_STATUSES: frozenset[str] = frozenset({"done", "error", "cancelled"})


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _apply_task_update_locked(task_id: str, **fields) -> None:
    """Mutate ``_install_tasks[task_id]`` in place; caller MUST hold the lock.

    Split out of :func:`_update_task` so the worker success-path can compose
    a cancel-event recheck and the status write atomically under one lock
    acquisition. See ``_run_install_task`` for the cancel-vs-success race
    that this enables fixing.
    """
    current = _install_tasks.get(task_id)
    if current is None:
        return
    current.update(fields)
    current["updated_at"] = _now_iso()
    # Stamp ``completed_at`` (monotonic) the first time the task enters a
    # terminal state. Used by :func:`_evict_old_install_tasks` — wall-clock
    # is not safe here (clock-skew / NTP-jumps) but ``time.monotonic`` is
    # immune.
    status = current.get("status")
    if status in _TERMINAL_STATUSES and current.get("completed_at") is None:
        current["completed_at"] = time.monotonic()


def _update_task(task_id: str, **fields) -> None:
    with _install_tasks_lock:
        _apply_task_update_locked(task_id, **fields)


def _evict_old_install_tasks() -> None:
    """Drop completed install tasks older than the retention window.

    Called at the top of :func:`start_install_task` and
    :func:`get_install_task` — both naturally bound the eviction frequency to
    the actual install-task traffic so the dict cannot grow without a poll
    actively walking it. Active (non-terminal) tasks are NEVER evicted, even
    if they have been queued/downloading for longer than the retention
    window — the wall-clock cap in :func:`_run_install_task` is responsible
    for terminating those.
    """
    now = time.monotonic()
    with _install_tasks_lock:
        evict_ids = [
            tid for tid, task in _install_tasks.items()
            if task.get("status") in _TERMINAL_STATUSES
            and task.get("completed_at") is not None
            and now - task["completed_at"] > _INSTALL_TASK_RETENTION_SEC
        ]
        for tid in evict_ids:
            _install_tasks.pop(tid, None)
            _install_task_handles.pop(tid, None)


def get_install_task(task_id: str) -> Optional[dict]:
    _evict_old_install_tasks()
    with _install_tasks_lock:
        task = _install_tasks.get(task_id)
        return dict(task) if task else None


def cancel_install_task(task_id: str) -> bool:
    """Signal cancellation for an in-flight install task.

    Returns ``True`` when a cancel signal was delivered to a non-terminal
    task, ``False`` if the task is unknown or already in a terminal state.
    The cancellation is best-effort: a Python thread cannot be hard-killed,
    and an in-flight ``requests.get`` only checks the event between chunks.
    The per-request timeout is the upper bound on how long a wedged socket
    keeps the worker alive after cancellation.
    """
    with _install_tasks_lock:
        task = _install_tasks.get(task_id)
        handle = _install_task_handles.get(task_id)
        if task is None or handle is None:
            return False
        if task.get("status") in _TERMINAL_STATUSES:
            return False
        cancel_event = handle.get("cancel_event")
    if cancel_event is None:
        return False
    cancel_event.set()
    _update_task(task_id, status="cancelled", error="Install cancelled by user")
    return True


def _run_install_task(
    task_id: str,
    major: int,
    cancel_event: threading.Event,
    started_at: float,
) -> None:
    install_major = effective_install_major(major)

    def _check_cancel_or_timeout() -> None:
        if cancel_event.is_set():
            raise RuntimeError("Java install was cancelled")
        if time.monotonic() - started_at > _INSTALL_TASK_MAX_RUNTIME_SEC:
            cancel_event.set()
            raise RuntimeError(
                f"Java install exceeded wall-clock cap of "
                f"{_INSTALL_TASK_MAX_RUNTIME_SEC}s"
            )

    def on_progress(downloaded: int, total: int) -> None:
        # Cheap watchdog tick on every progress report so a long stream still
        # respects the wall-clock cap without a separate timer thread.
        if time.monotonic() - started_at > _INSTALL_TASK_MAX_RUNTIME_SEC:
            cancel_event.set()
        _update_task(
            task_id,
            downloaded=downloaded,
            total=total,
        )

    try:
        _check_cancel_or_timeout()
        _update_task(task_id, status="downloading", downloaded=0, total=0)
        archive = download_java(
            install_major,
            progress_callback=on_progress,
            cancel_event=cancel_event,
        )
        _check_cancel_or_timeout()
        _update_task(task_id, status="installing")
        java_path = install_java(install_major, archive)
        # Atomic cancel-vs-success finalisation under the lock. Without it, a
        # concurrent ``cancel_install_task`` could interleave between the
        # is_set() check and the ``status="done"`` write — either direction
        # could clobber the other's terminal status. The lock-held recheck
        # closes the race: a cancel that wins the lock first will already
        # have flipped status to ``cancelled``, and our finalise branches
        # honour ``cancel_event``.
        with _install_tasks_lock:
            if cancel_event.is_set():
                _apply_task_update_locked(
                    task_id,
                    status="cancelled",
                    error="Install cancelled by user",
                )
            else:
                _apply_task_update_locked(
                    task_id,
                    status="done",
                    java_path=java_path,
                    install_major=install_major,
                )
    except Exception as exc:  # pragma: no cover - runtime/network path
        # Preserve cancel state if it was already set: a cancel that races
        # with a download abort should report ``cancelled``, not ``error``.
        with _install_tasks_lock:
            current = _install_tasks.get(task_id)
            already_cancelled = (
                current is not None and current.get("status") == "cancelled"
            )
        if not already_cancelled:
            _update_task(task_id, status="error", error=str(exc))


def start_install_task(major: int) -> str:
    """Kick off an install in a background thread and return the task id."""
    _evict_old_install_tasks()
    install_major = effective_install_major(major)
    task_id = uuid.uuid4().hex
    cancel_event = threading.Event()
    started_at = time.monotonic()
    with _install_tasks_lock:
        _install_tasks[task_id] = {
            "status": "queued",
            "requested_major": int(major),
            "install_major": install_major,
            "substituted": install_major != int(major),
            "downloaded": 0,
            "total": 0,
            "java_path": None,
            "error": None,
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
            # ``completed_at`` is a monotonic timestamp (set on terminal
            # transition) used for retention-window arithmetic. Distinct
            # from the ISO ``updated_at`` to avoid wall-clock-skew bugs.
            "completed_at": None,
            "max_runtime_sec": _INSTALL_TASK_MAX_RUNTIME_SEC,
        }
        _install_task_handles[task_id] = {
            "cancel_event": cancel_event,
            "started_at": started_at,
            # Thread reference is published below once the thread exists.
            "thread": None,
        }

    thread = threading.Thread(
        target=_run_install_task,
        args=(task_id, install_major, cancel_event, started_at),
        name=f"java-install-{install_major}",
        daemon=True,
    )
    with _install_tasks_lock:
        handle = _install_task_handles.get(task_id)
        if handle is not None:
            handle["thread"] = thread
    thread.start()
    return task_id
