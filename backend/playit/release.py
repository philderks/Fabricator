"""Pinned playit-agent release: version, per-asset sha256, arch mapping.

The single source of truth for WHICH playit binaries Fabricator trusts. Read by

  * :mod:`backend.playit.provision` — to download and verify them, and
  * :mod:`backend.playit.binary`    — to classify whatever is already on disk.

Bumping ``PLAYIT_VERSION`` requires refreshing EVERY digest in ``SHA256`` from
https://api.github.com/repos/playit-cloud/playit-agent/releases/tags/<ver>
(the ``digest`` field on each asset). Provisioning fails closed on a mismatch,
so a half-updated pin breaks loudly rather than installing something unchecked.

playit publishes these assets for Linux only — every other platform resolves to
no arch and the caller degrades gracefully (Windows never gets this far; see
``agent.get_status``).
"""
from __future__ import annotations

import platform
from typing import Optional

# Bump together with every digest below.
PLAYIT_VERSION = "v1.0.5"

_DOWNLOAD_BASE = (
    "https://github.com/playit-cloud/playit-agent/releases/download/{version}/{asset}"
)

# Executable names as Fabricator installs (and discovers) them, independent of
# the arch-suffixed asset names on the release page.
DAEMON_NAME = "playit"
CLI_NAME = "playit-cli"
BINARY_NAMES = (DAEMON_NAME, CLI_NAME)

# asset name -> sha256. Verified against the GitHub release API; identical to
# the PLAYIT_SHA256 table in tools/install.sh (which stays the installer's copy
# until that script is migrated onto `python -m backend.playit.provision`).
SHA256: dict[str, str] = {
    "playit-linux-amd64":       "217bd341b3ea88f982ce45bb68aa8b795bf8d6866be841cc675d36f3c6b90277",
    "playit-linux-aarch64":     "7cfcf151581076295a210d56d2015a4b0b1ef26f4b3d4b753424c5d96eca6d95",
    "playit-linux-armv7":       "140a8a2b49ee01d0562cd1a2c898dc641d640057c62cf6172724587cdf08828a",
    "playit-linux-i686":        "c7b84d00aeb2735645230d5d9479a90a6bb2999f679d48613c91def30758580b",
    "playit-cli-linux-amd64":   "1a3e6f2acfef345dafe32daa280ce4dc62e39601ff083bb5b88ea28ae7e5168c",
    "playit-cli-linux-aarch64": "0b7a8d580727a1d2ff249ab96eab5233b7973720f6df245764016f4436d3ff70",
    "playit-cli-linux-armv7":   "98855142ef50d49cb85b84b61531423ffac11bf78eafa250f43453e9e14cbe1e",
    "playit-cli-linux-i686":    "571a4e22148e3c6c8a0d90ad3dbf4a7d43e18d1bd40e367cb755a5e355903775",
}

# platform.machine() -> playit asset arch suffix. Mirrors the `uname -m` case
# in tools/install.sh, plus the aliases Python reports on some hosts (e.g.
# "arm64" under Docker/QEMU on Apple silicon, "amd64" on a few distros).
_MACHINE_TO_ARCH = {
    "x86_64":  "amd64",
    "amd64":   "amd64",
    "aarch64": "aarch64",
    "arm64":   "aarch64",
    "armv7l":  "armv7",
    "armv7":   "armv7",
    "armv8l":  "armv7",
    "i386":    "i686",
    "i486":    "i686",
    "i586":    "i686",
    "i686":    "i686",
}


def resolve_arch(machine: Optional[str] = None) -> Optional[str]:
    """Map a machine string to a playit asset arch, or None if unsupported.

    Defaults to the running host's ``platform.machine()``. Not cached: the
    override argument exists so tests can exercise every branch, and the
    uncached path costs one syscall on a status poll at worst.
    """
    raw = (machine if machine is not None else platform.machine()).strip().lower()
    return _MACHINE_TO_ARCH.get(raw)


def asset_name(binary: str, arch: str) -> str:
    """Release-asset name for an installed binary name + arch.

    ``("playit", "amd64")`` -> ``"playit-linux-amd64"``.
    """
    return f"{binary}-linux-{arch}"


def asset_url(asset: str) -> str:
    """Full GitHub download URL for a release asset of the pinned version."""
    return _DOWNLOAD_BASE.format(version=PLAYIT_VERSION, asset=asset)


def expected_sha256(binary: str, arch: Optional[str] = None) -> Optional[str]:
    """Pinned digest for ``binary`` on ``arch`` (default: this host's arch).

    None when the arch is unsupported or the table has no entry for it — both
    mean "we cannot vouch for this binary", never "any binary will do".
    """
    if arch is None:
        arch = resolve_arch()
    if arch is None:
        return None
    return SHA256.get(asset_name(binary, arch))
