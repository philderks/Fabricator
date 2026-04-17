"""Cross-platform helper utilities for Fabricator."""
from __future__ import annotations

import platform
import shlex
import tempfile
from functools import lru_cache
from pathlib import Path
from typing import List


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
