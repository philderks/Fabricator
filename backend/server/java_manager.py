"""Managed Java runtime download, install and resolution.

Single source of truth for locating a JDK that is compatible with a given
Minecraft server. Falls back to downloading the Temurin (Adoptium) build when
no suitable system Java is available. Installs are performed entirely under
Fabricator's own data directory so no elevated permissions are required.
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import tarfile
import threading
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

import requests

from backend.core.config import get_config
from backend.server.java_compat import resolve_required_java
from backend.utils import platform as platform_utils


ADOPTIUM_API = "https://api.adoptium.net/v3/assets/latest/{major}/hotspot"

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
    """Invoke ``java -version`` and return the detected major, or None."""
    try:
        result = subprocess.run(
            ["java", "-version"],
            capture_output=True,
            text=True,
            **platform_utils.subprocess_no_window_kwargs(),
        )
    except FileNotFoundError:
        return None
    output = (result.stdout or "") + (result.stderr or "")
    if result.returncode != 0:
        return None
    match = re.search(r'version "([^"]+)"', output)
    if not match:
        return None
    raw = match.group(1).strip()
    if raw.startswith("1."):
        parts = raw.split(".")
        if len(parts) > 1 and parts[1].isdigit():
            return int(parts[1])
        return None
    major_match = re.match(r"^(\d+)", raw)
    if not major_match:
        return None
    return int(major_match.group(1))


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
    """
    install_major = effective_install_major(major)
    url = ADOPTIUM_API.format(major=install_major)
    try:
        response = requests.get(url, timeout=30)
    except requests.RequestException as exc:
        raise RuntimeError(
            f"Failed to reach Adoptium API for Java {install_major}: {exc}"
        ) from exc

    if response.status_code != 200:
        raise RuntimeError(
            f"Adoptium API returned HTTP {response.status_code} for Java {install_major}"
        )

    try:
        assets = response.json()
    except ValueError as exc:
        raise RuntimeError(
            f"Adoptium API returned invalid JSON for Java {install_major}"
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
) -> Path:
    """Download the Temurin JDK archive for ``major`` to a temp file.

    Verifies the SHA-256 checksum against the Adoptium API. Returns the path
    to the downloaded archive (not yet extracted). Raises ``RuntimeError`` on
    any network, IO or integrity failure.
    """
    asset = adoptium_asset_url(major)
    download_dir = _download_root()
    target = download_dir / asset["filename"]

    hasher = hashlib.sha256()
    total = asset["size_bytes"] or 0
    downloaded = 0

    try:
        with requests.get(asset["download_url"], stream=True, timeout=60) as response:
            if response.status_code != 200:
                raise RuntimeError(
                    f"Adoptium download returned HTTP {response.status_code}"
                )
            content_length = response.headers.get("Content-Length")
            if not total and content_length and content_length.isdigit():
                total = int(content_length)
            if progress_callback:
                progress_callback(0, total)
            with open(target, "wb") as fh:
                for chunk in response.iter_content(chunk_size=1024 * 256):
                    if not chunk:
                        continue
                    fh.write(chunk)
                    hasher.update(chunk)
                    downloaded += len(chunk)
                    if progress_callback:
                        progress_callback(downloaded, total or downloaded)
    except requests.RequestException as exc:
        _safe_unlink(target)
        raise RuntimeError(f"Failed downloading Java archive: {exc}") from exc

    expected = (asset.get("checksum") or "").lower()
    actual = hasher.hexdigest()
    if expected and expected != actual:
        _safe_unlink(target)
        raise RuntimeError(
            "Java archive checksum mismatch: expected "
            f"{expected[:12]}..., got {actual[:12]}..."
        )

    return target


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
            _safe_extract_zip(zf, staging)
    else:
        raise RuntimeError(f"Unsupported archive format: {archive.name}")


def _safe_extract_tar(tar: tarfile.TarFile, destination: Path) -> None:
    destination = destination.resolve()
    for member in tar.getmembers():
        member_path = (destination / member.name).resolve()
        if not str(member_path).startswith(str(destination)):
            raise RuntimeError("Archive contains invalid paths")
    tar.extractall(destination)


def _safe_extract_zip(zf: zipfile.ZipFile, destination: Path) -> None:
    destination = destination.resolve()
    for member in zf.infolist():
        member_path = (destination / member.filename).resolve()
        if not str(member_path).startswith(str(destination)):
            raise RuntimeError("Archive contains invalid paths")
        if member.is_dir():
            member_path.mkdir(parents=True, exist_ok=True)
            continue
        member_path.parent.mkdir(parents=True, exist_ok=True)
        with zf.open(member, "r") as source, open(member_path, "wb") as sink:
            shutil.copyfileobj(source, sink)


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


def _update_task(task_id: str, **fields) -> None:
    with _install_tasks_lock:
        current = _install_tasks.get(task_id)
        if current is None:
            return
        current.update(fields)
        current["updated_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def get_install_task(task_id: str) -> Optional[dict]:
    with _install_tasks_lock:
        task = _install_tasks.get(task_id)
        return dict(task) if task else None


def _run_install_task(task_id: str, major: int) -> None:
    install_major = effective_install_major(major)

    def on_progress(downloaded: int, total: int) -> None:
        _update_task(
            task_id,
            downloaded=downloaded,
            total=total,
        )

    try:
        _update_task(task_id, status="downloading", downloaded=0, total=0)
        archive = download_java(install_major, progress_callback=on_progress)
        _update_task(task_id, status="installing")
        java_path = install_java(install_major, archive)
        _update_task(
            task_id,
            status="done",
            java_path=java_path,
            install_major=install_major,
        )
    except Exception as exc:  # pragma: no cover - runtime/network path
        _update_task(task_id, status="error", error=str(exc))


def start_install_task(major: int) -> str:
    """Kick off an install in a background thread and return the task id."""
    install_major = effective_install_major(major)
    task_id = uuid.uuid4().hex
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
            "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "updated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }

    thread = threading.Thread(
        target=_run_install_task,
        args=(task_id, install_major),
        name=f"java-install-{install_major}",
        daemon=True,
    )
    thread.start()
    return task_id
