"""Binary discovery and CLI subprocess wrapper for playit.gg.

The agent code uses two binaries from playit-cloud/playit-agent (pinned to
v1.0.5 by tools/install.sh):

* `playit`      — the daemon (playitd). Long-running tunnel process.
* `playit-cli`  — orchestrator. We invoke it for the headless claim flow
                  (`claim generate`, `claim url`, `claim exchange`) and as a
                  status cross-check against the running daemon.

Discovery probes $PATH first so dev-machine installs (e.g. `apt install
playit`) take precedence over the installer-managed binaries.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from backend.utils import platform as platform_utils

logger = logging.getLogger(__name__)

_RUNTIME_DIR_DEFAULT = "/var/lib/fabricator/playit"


def runtime_dir() -> Path:
    """Directory the daemon uses for secret/socket/log files.

    All three live together because the systemd unit only grants the service
    user write access to /var/lib/fabricator. Dev override via env var.
    """
    return Path(os.environ.get("PLAYIT_RUNTIME_DIR") or _RUNTIME_DIR_DEFAULT)


def secret_path() -> Path:
    return runtime_dir() / "playit.toml"


def socket_path() -> Path:
    return runtime_dir() / "playit.sock"


def log_path() -> Path:
    return runtime_dir() / "playitd.log"


def enabled_state_path() -> Path:
    """Persisted desired-state file: written when the user toggles the tunnel
    on/off so the choice survives a service restart. Lives in the runtime dir
    (service-user-writable), unlike the root-owned env file."""
    return runtime_dir() / "playit.enabled"


def runtime_dir_writable() -> bool:
    """True if the runtime dir is writable, or could be created (its nearest
    existing ancestor is writable). Non-mutating.

    Used at startup to warn early when the playit runtime dir isn't usable —
    the common dev case is PLAYIT_RUNTIME_DIR unset, so it defaults to
    /var/lib/fabricator/playit, which a non-service user can't create. Without
    a writable dir the tunnel can't persist its secret after a claim and the
    agent silently shows offline on playit.gg.
    """
    probe = runtime_dir()
    while not probe.exists():
        parent = probe.parent
        if parent == probe:          # reached the filesystem root, nothing exists
            return False
        probe = parent
    return os.access(probe, os.W_OK)


def _first_executable(*candidates: str) -> Optional[str]:
    for c in candidates:
        if os.access(c, os.X_OK):
            return c
    return None


def find_daemon() -> Optional[str]:
    """Locate the `playit` daemon binary, or None if not installed."""
    return shutil.which("playit") or _first_executable(
        "/usr/local/bin/playit", "/usr/bin/playit"
    )


def find_cli() -> Optional[str]:
    """Locate the `playit-cli` orchestrator binary, or None if not installed."""
    return shutil.which("playit-cli") or _first_executable(
        "/usr/local/bin/playit-cli", "/usr/bin/playit-cli"
    )


def binary_verified() -> bool:
    """True when install.sh successfully sha256-verified the pinned binaries."""
    return os.environ.get("PLAYIT_BINARY_VERIFIED", "").strip().lower() == "true"


def run_cli(
    *args: str,
    timeout: int = 30,
    sensitive: bool = False,
) -> subprocess.CompletedProcess:
    """Synchronously invoke `playit-cli <args...>` and return the result.

    Used for short, one-shot calls (e.g. `claim generate`, `claim url`,
    `status`). The secret-bearing `claim exchange` does NOT use this helper —
    it spawns Popen directly in agent.py so stop() can cancel it.

    sensitive=True
        stdout MAY contain secret material. The wrapper logs only `args` and
        the returncode at DEBUG level; it never logs stdout or stderr from
        this call, and never includes them in the CompletedProcess's repr.
        Callers MUST handle the returned stdout with the same discipline.
    """
    cli = find_cli()
    if cli is None:
        raise FileNotFoundError("playit-cli binary not found on PATH or /usr/local/bin")

    cmd = [cli, *args]
    if not sensitive:
        logger.debug("playit-cli: %s", " ".join(args))
    else:
        # Log only the subcommand name (always `args[0]`) — never the full
        # arglist, since e.g. claim codes are short-lived but still secret.
        logger.debug("playit-cli: <sensitive subcommand %r>", args[0] if args else "<none>")

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        **platform_utils.subprocess_no_window_kwargs(),
    )
    if not sensitive:
        logger.debug("playit-cli rc=%d", result.returncode)
    return result
