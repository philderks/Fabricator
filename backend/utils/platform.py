"""Cross-platform helper utilities for Fabricator."""
from __future__ import annotations

import logging
import os
import platform
import shlex
import subprocess
import tempfile
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List


logger = logging.getLogger(__name__)


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
    """Return the Adoptium-compatible architecture label for this machine.

    Falls back to ``'x64'`` for unknown machine strings (e.g. ``'arm64e'``,
    ``'riscv64'``, ``'ppc64le'``) and emits a WARNING — without that signal
    a mis-detected machine surfaces only mid-install as an Adoptium 404.
    """
    machine = platform.machine().lower()
    mapping = {
        'x86_64': 'x64',
        'amd64': 'x64',
        'aarch64': 'aarch64',
        'arm64': 'aarch64',
        'armv7l': 'arm',
        'armv8l': 'arm',
    }
    label = mapping.get(machine)
    if label is None:
        logger.warning(
            "Unknown CPU architecture %r; defaulting to 'x64' — "
            "Adoptium downloads may 404 on this host.",
            machine,
        )
        return 'x64'
    return label


def split_command(command: str) -> List[str]:
    """Split shell commands with the correct POSIX flag for the host OS."""
    if not command:
        return []
    return shlex.split(command, posix=not is_windows())


@lru_cache(maxsize=1)
def appdata_dir() -> Path:
    """Return the per-user Fabricator data directory.

    Per-platform conventions:

    - Windows: ``%APPDATA%\\Fabricator`` (typically ``~/AppData/Roaming/Fabricator``)
    - POSIX:   ``~/.fabricator``

    POSIX uses ``~/.fabricator`` (not XDG ``~/.local/share/fabricator``) for
    cross-platform symmetry with ``%APPDATA%`` — both sit at the user-home
    root rather than under a nested data-directory hierarchy, which keeps
    the PyInstaller-bundled .exe and POSIX dev install pointing at
    structurally equivalent locations.

    Override via the ``FABRICATOR_APPDATA`` environment variable for
    testing or non-default installs. The override path is ``~``-expanded
    and created if missing; no platform branch runs when an override is
    set.

    Cached via ``lru_cache`` so the ``mkdir`` runs once per process; this
    function is hit multiple times per request via ``core.config`` defaults.
    Call ``appdata_dir.cache_clear()`` in tests that monkey-patch ``HOME``,
    ``APPDATA``, or ``FABRICATOR_APPDATA`` between calls.
    """
    override = os.environ.get("FABRICATOR_APPDATA")
    if override:
        target = Path(override).expanduser()
    elif is_windows():
        raw = os.environ.get("APPDATA")
        base = Path(raw) if raw else Path.home() / "AppData" / "Roaming"
        target = base / "Fabricator"
    else:
        target = Path.home() / ".fabricator"
    first_create = not target.exists()
    target.mkdir(parents=True, exist_ok=True)
    if first_create:
        logger.info("Fabricator data directory: %s", target)
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
