"""Cross-platform helper utilities for Fabricator."""
from __future__ import annotations

import os
import platform
import shlex
import subprocess
import tempfile
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional


@lru_cache(maxsize=1)
def _system_name() -> str:
    """Return the normalized platform.system() string."""
    return platform.system().strip().lower()


def is_windows() -> bool:
    """True when running on Windows hosts."""
    return _system_name() == "windows"


def is_linux() -> bool:
    """True when running on Linux hosts."""
    return _system_name() == "linux"


def is_macos() -> bool:
    """True when running on macOS hosts."""
    return _system_name() == "darwin"


def platform_label() -> str:
    """Return the cached platform label (windows/linux/darwin/other)."""
    return _system_name()


@lru_cache(maxsize=1)
def arch_label() -> str:
    """Return the Adoptium-compatible architecture label for this machine."""
    machine = platform.machine().lower()
    mapping = {
        'x86_64': 'x64',
        'amd64': 'x64',
        'aarch64': 'aarch64',
        'arm64': 'aarch64',
        'armv7l': 'arm',
        'armv8l': 'arm',
    }
    return mapping.get(machine, 'x64')


def split_command(command: str) -> List[str]:
    """Split shell commands with the correct POSIX flag for the host OS."""
    if not command:
        return []
    return shlex.split(command, posix=not is_windows())


def appdata_dir() -> Optional[Path]:
    """Return the per-user Fabricator data directory on Windows, else None.

    On Windows the .exe is typically launched from Downloads or another
    transient location, so user data must live in a stable, writable spot.
    Returns ``%APPDATA%\\Fabricator`` (creating it if missing). On POSIX
    deployments paths are managed by ``install.sh`` / systemd, so this
    returns ``None`` and callers keep their existing behavior.
    """
    if not is_windows():
        return None
    raw = os.environ.get("APPDATA")
    base = Path(raw) if raw else Path.home() / "AppData" / "Roaming"
    target = base / "Fabricator"
    target.mkdir(parents=True, exist_ok=True)
    return target


def subprocess_no_window_kwargs() -> Dict[str, Any]:
    """Return subprocess kwargs that prevent a child console window on Windows.

    When Fabricator runs as a windowless PyInstaller bundle, child processes
    (Java server, ``java -version`` probes) would otherwise spawn an empty
    console window. Spreading these kwargs into ``Popen``/``run`` suppresses it.
    No-op on POSIX.
    """
    if is_windows():
        return {"creationflags": subprocess.CREATE_NO_WINDOW}
    return {}


def temp_directory(name: str | None = None, ensure_exists: bool = True) -> Path:
    """Return a temp directory path with optional child name.

    Args:
        name: Optional folder name under the system temp dir.
        ensure_exists: When True, mkdir the directory before returning.
    """
    temp_base = Path(tempfile.gettempdir())
    target = temp_base / name if name else temp_base
    if ensure_exists:
        target.mkdir(parents=True, exist_ok=True)
    return target
