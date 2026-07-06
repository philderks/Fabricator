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

    Resolution order:
      1. PLAYIT_RUNTIME_DIR, if set (production systemd unit + explicit dev).
      2. /var/lib/fabricator/playit when it's writable/creatable — the systemd
         installer (tools/install.sh) creates it owned by the service user.
      3. Otherwise (dev / non-service run, where /var/lib isn't writable by the
         current user) the per-user data dir ~/.fabricator/playit, so the tunnel
         can actually persist its secret instead of failing every write and
         showing offline on playit.gg.

    Production is unchanged: the service user owns the /var/lib path, so step 2
    matches and the fallback never triggers.
    """
    env = os.environ.get("PLAYIT_RUNTIME_DIR")
    if env:
        return Path(env)
    default = Path(_RUNTIME_DIR_DEFAULT)
    if _writable_or_creatable(default):
        return default
    return platform_utils.appdata_dir() / "playit"


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


def _writable_or_creatable(path: Path) -> bool:
    """True if `path` is writable, or its nearest existing ancestor is (so it
    could be created). Non-mutating — used to pick and validate the runtime dir."""
    probe = path
    while not probe.exists():
        parent = probe.parent
        if parent == probe:          # reached the filesystem root, nothing exists
            return False
        probe = parent
    return os.access(probe, os.W_OK)


def runtime_dir_writable() -> bool:
    """True if the resolved runtime dir is usable. After the dev fallback in
    runtime_dir() this is normally True; kept as a startup guard for the
    pathological case where even the per-user data dir isn't writable."""
    return _writable_or_creatable(runtime_dir())


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
