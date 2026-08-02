"""Download + verify the pinned playit-agent binaries (daemon and CLI).

A Python port of ``install_playit_binaries()`` from tools/install.sh, sharing
one copy of the pin (:mod:`backend.playit.release`). Two callers:

  * **Docker build** — ``python -m backend.playit.provision --dest /usr/local/bin``
    bakes the binaries into the image. tools/ is deliberately not copied into
    the image, so install.sh cannot do it there and playit was simply absent
    (issue #55).
  * **agent.start()** — self-heals any install whose binaries are missing, into
    ``runtime_dir()/bin``: an install.sh run whose download failed (it warns and
    continues by design), a pip/dev checkout, or an image predating the bake.

Fails closed. A download error, an unsupported platform, or a sha256 mismatch
raises :class:`ProvisionError` and leaves nothing behind — a partially written
binary is never moved into place, and an existing good binary is never replaced
by an unverified one.
"""
from __future__ import annotations

import argparse
import hashlib
import logging
import os
import sys
import threading
import time
from pathlib import Path
from typing import Optional

import requests

from backend.utils import platform as platform_utils

from . import release

logger = logging.getLogger(__name__)

# Per-asset network budget. The binaries are ~6 MB each, so a slow-but-alive
# link still finishes well inside this; a black-holed connection does not.
_DOWNLOAD_TIMEOUT_SEC = 120
_CHUNK_BYTES = 64 * 1024

# Transient-failure retries, matching the convention used by the loader
# installers and java_manager (_ADOPTIUM_RETRIES).
_RETRIES = 3
_RETRY_BACKOFF_SEC = 1.5

# Serialises concurrent provisioning. Two dashboard tabs toggling the agent at
# once must not race on the same temp file / os.replace.
_lock = threading.Lock()


class ProvisionError(Exception):
    """Provisioning could not complete. Message is user-facing (surfaced as
    the agent's ``error_reason``), so it must stay free of paths that only
    make sense to a developer."""


def sha256_file(path: Path) -> Optional[str]:
    """Hex sha256 of ``path``, or None if it cannot be read.

    Shared with binary.py's trust classification so both sides hash the same
    way. Streams: these are multi-MB files and this runs on a status poll.
    """
    hasher = hashlib.sha256()
    try:
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(_CHUNK_BYTES), b""):
                hasher.update(chunk)
    except OSError:
        return None
    return hasher.hexdigest()


def default_dest() -> Path:
    """Where runtime provisioning installs to: ``runtime_dir()/bin``.

    Deliberately NOT /usr/local/bin: under systemd the service runs with
    ``ProtectSystem=strict`` (tools/install.sh), and in Docker it runs as an
    unprivileged uid — neither can write there. The runtime dir is the one
    location every install method guarantees is writable by the service user.
    """
    from . import binary as playit_binary  # local: binary.py imports nothing here

    return playit_binary.runtime_dir() / "bin"


def _installed_ok(path: Path, expected: str) -> bool:
    """True when ``path`` is an executable file already matching the pin."""
    if not os.access(path, os.X_OK) or not path.is_file():
        return False
    return sha256_file(path) == expected


def _download_verified(url: str, expected: str, tmp_path: Path) -> None:
    """Stream ``url`` to ``tmp_path`` and verify its digest, with retries.

    Hashing happens during the stream so the file is never read twice. On a
    digest mismatch the temp file is removed and ProvisionError is raised —
    mismatches are NOT retried, since a wrong pin will never come right.
    """
    last_error: Optional[str] = None

    for attempt in range(1, _RETRIES + 1):
        hasher = hashlib.sha256()
        try:
            with requests.get(url, stream=True, timeout=_DOWNLOAD_TIMEOUT_SEC) as response:
                response.raise_for_status()
                with open(tmp_path, "wb") as handle:
                    for chunk in response.iter_content(chunk_size=_CHUNK_BYTES):
                        if chunk:
                            hasher.update(chunk)
                            handle.write(chunk)
        except requests.RequestException as exc:
            last_error = str(exc)
            tmp_path.unlink(missing_ok=True)
            if attempt < _RETRIES:
                logger.warning(
                    "playit: download attempt %d/%d failed (%s); retrying",
                    attempt, _RETRIES, exc,
                )
                time.sleep(_RETRY_BACKOFF_SEC * attempt)
                continue
            raise ProvisionError(
                f"could not download the playit agent from GitHub ({last_error})"
            ) from exc
        except OSError as exc:
            tmp_path.unlink(missing_ok=True)
            raise ProvisionError(f"could not write the playit binary ({exc})") from exc

        actual = hasher.hexdigest()
        if actual != expected:
            tmp_path.unlink(missing_ok=True)
            raise ProvisionError(
                "sha256 mismatch on the downloaded playit binary — refusing to install it"
            )
        return


def ensure_binaries(dest: Optional[Path] = None) -> Path:
    """Make the pinned daemon + CLI present and verified in ``dest``.

    Returns the destination directory. Idempotent and cheap on the happy path:
    binaries already matching the pin are left untouched (this is also what
    keeps a rebuild or a redundant start() from re-fetching from GitHub).

    Raises ProvisionError on an unsupported platform/arch, a download failure,
    or a digest mismatch.
    """
    if not platform_utils.is_linux():
        raise ProvisionError("the playit agent is published for Linux only")

    arch = release.resolve_arch()
    if arch is None:
        raise ProvisionError(
            f"no playit build for this architecture ({os.uname().machine})"
        )

    dest = Path(dest) if dest is not None else default_dest()

    with _lock:
        try:
            dest.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise ProvisionError(f"cannot create the install directory ({exc})") from exc

        for name in release.BINARY_NAMES:
            expected = release.expected_sha256(name, arch)
            if expected is None:  # unreachable while the pin table is complete
                raise ProvisionError(f"no pinned checksum for {name} on {arch}")

            target = dest / name
            if _installed_ok(target, expected):
                logger.debug("playit: %s already present and verified", target)
                continue

            asset = release.asset_name(name, arch)
            logger.info("playit: downloading %s %s", asset, release.PLAYIT_VERSION)

            # Temp file lives in `dest` so the swap below is a same-filesystem
            # rename (atomic): a reader either sees the old binary or the fully
            # written new one, never a truncated file mid-download.
            tmp_path = dest / f".{name}.{os.getpid()}.tmp"
            _download_verified(release.asset_url(asset), expected, tmp_path)

            try:
                tmp_path.chmod(0o755)
                os.replace(tmp_path, target)
            except OSError as exc:
                tmp_path.unlink(missing_ok=True)
                raise ProvisionError(f"cannot install the playit binary ({exc})") from exc

            logger.info("playit: installed %s (sha256 verified)", target)

    return dest


def main(argv: Optional[list[str]] = None) -> int:
    """CLI entry point (``python -m backend.playit.provision``).

    Used by the Docker build. Exits non-zero on failure so a broken or
    unreachable pin fails the image build rather than silently shipping an
    image without playit — the exact failure mode of issue #55.
    """
    parser = argparse.ArgumentParser(
        prog="python -m backend.playit.provision",
        description=f"Install the pinned playit-agent binaries ({release.PLAYIT_VERSION}).",
    )
    parser.add_argument(
        "--dest",
        default=None,
        help="install directory (default: the Fabricator playit runtime dir)",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    try:
        dest = ensure_binaries(Path(args.dest) if args.dest else None)
    except ProvisionError as exc:
        print(f"playit provisioning failed: {exc}", file=sys.stderr)
        return 1
    print(f"playit {release.PLAYIT_VERSION} installed to {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
