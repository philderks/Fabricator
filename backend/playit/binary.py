"""Binary discovery and CLI subprocess wrapper for playit.gg.

The agent code uses two binaries from playit-cloud/playit-agent (pinned in
backend/playit/release.py):

* `playit`      — the daemon (playitd). Long-running tunnel process.
* `playit-cli`  — orchestrator. We invoke it for the headless claim flow
                  (`claim generate`, `claim url`, `claim exchange`) and as a
                  status cross-check against the running daemon.

Discovery probes $PATH first so dev-machine installs (e.g. `apt install
playit`) take precedence over the installer-managed binaries, then the two
directories Fabricator itself installs into (see MANAGED_BIN_DIRS).
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Optional

from backend.utils import platform as platform_utils

from . import release

logger = logging.getLogger(__name__)

_RUNTIME_DIR_DEFAULT = "/var/lib/fabricator/playit"

# Directories whose contents Fabricator put there itself: tools/install.sh and
# the Docker build write /usr/local/bin, runtime provisioning writes
# runtime_dir()/bin. A binary here that does NOT match the pin is a real
# anomaly (tampering, a half-finished update); the same mismatch elsewhere just
# means the operator supplied their own build. binary_trust() tells them apart.
_SYSTEM_MANAGED_BIN_DIR = "/usr/local/bin"


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


def managed_bin_dir() -> Path:
    """Directory runtime provisioning installs into. Volume-backed in Docker,
    inside ReadWritePaths under systemd — the one place writable by the service
    user on every install method."""
    return runtime_dir() / "bin"


def _first_executable(*candidates: str) -> Optional[str]:
    for c in candidates:
        if os.access(c, os.X_OK):
            return c
    return None


def _find(name: str) -> Optional[str]:
    """Resolve an installed playit binary by name, or None.

    $PATH wins (operator-supplied builds take precedence), then the two
    Fabricator-managed locations, then /usr/bin for distro packages that are
    somehow off $PATH.
    """
    return shutil.which(name) or _first_executable(
        f"{_SYSTEM_MANAGED_BIN_DIR}/{name}",
        str(managed_bin_dir() / name),
        f"/usr/bin/{name}",
    )


def find_daemon() -> Optional[str]:
    """Locate the `playit` daemon binary, or None if not installed."""
    return _find(release.DAEMON_NAME)


def find_cli() -> Optional[str]:
    """Locate the `playit-cli` orchestrator binary, or None if not installed."""
    return _find(release.CLI_NAME)


# ---------------------------------------------------------------------------
# Trust classification
# ---------------------------------------------------------------------------

TRUST_VERIFIED = "verified"      # both binaries match the pinned release
TRUST_UNVERIFIED = "unverified"  # in a dir WE manage, but not the pinned build
TRUST_SYSTEM = "system"          # operator-supplied (distro package, custom $PATH)
TRUST_MISSING = "missing"        # nothing installed — the agent error covers it

# Digest cache. /api/playit/status is polled every ~3s and each binary is ~6 MB,
# so re-hashing per poll would burn ~4 MB/s of I/O forever. Keyed by the
# identity triple: a replaced binary always changes mtime_ns or size.
_digest_cache: dict[str, tuple[int, int, Optional[str]]] = {}
_digest_lock = threading.Lock()


def _cached_sha256(path: str) -> Optional[str]:
    try:
        stat = os.stat(path)
    except OSError:
        return None
    key = (stat.st_mtime_ns, stat.st_size)

    with _digest_lock:
        cached = _digest_cache.get(path)
        if cached is not None and cached[:2] == key:
            return cached[2]

    # Hashed outside the lock: a concurrent status poll may duplicate the work
    # once, which is far cheaper than serialising every caller behind ~6 MB of
    # I/O while holding a lock the rest of the module's fast paths need.
    from .provision import sha256_file  # local: provision imports this module

    digest = sha256_file(Path(path))
    with _digest_lock:
        _digest_cache[path] = (*key, digest)
    return digest


def _is_managed_path(path: str) -> bool:
    """True when `path` lives in a directory Fabricator installs into."""
    parent = os.path.dirname(os.path.abspath(path))
    return parent in {_SYSTEM_MANAGED_BIN_DIR, str(managed_bin_dir())}


def binary_trust() -> str:
    """How much we can vouch for the playit binaries currently resolved.

    Computed from the bytes on disk rather than declared by the installer: the
    old PLAYIT_BINARY_VERIFIED env var was written once at install time and
    stayed "true" even if the binary was later replaced, and was never set at
    all for Docker installs (issue #55).

    `system` exists so an operator who installed playit themselves (e.g. `apt
    install playit`, which discovery deliberately prefers) is told we did not
    verify it, without being warned about a setup that is working as intended.
    """
    daemon = find_daemon()
    cli = find_cli()
    if daemon is None or cli is None:
        return TRUST_MISSING

    resolved = ((release.DAEMON_NAME, daemon), (release.CLI_NAME, cli))
    if all(_matches_pin(name, path) for name, path in resolved):
        return TRUST_VERIFIED

    if all(_is_managed_path(path) for _, path in resolved):
        return TRUST_UNVERIFIED
    return TRUST_SYSTEM


def _matches_pin(name: str, path: str) -> bool:
    """True only on a positive digest match. An unsupported arch (no pinned
    digest) or an unreadable file both yield None, and None == None must NOT
    read as verified — hence the explicit guard."""
    expected = release.expected_sha256(name)
    if expected is None:
        return False
    return _cached_sha256(path) == expected


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
