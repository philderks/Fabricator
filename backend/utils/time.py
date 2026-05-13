"""ISO-Z wire-format helpers.

Centralises the ``YYYY-MM-DDTHH:MM:SS[.ffffff]Z`` timestamp format used by
the frontend and the storage / install-progress / java-manager surfaces.

Python's :func:`datetime.isoformat` emits ``+00:00`` for UTC; the frontend
parses the ``Z`` suffix, so producers replace the offset. The 11 inline
duplicates of this idiom across the backend collapse to a single call here.
"""
from __future__ import annotations

from datetime import datetime, timezone


def iso_z_now() -> str:
    """Return the current UTC time as ``YYYY-MM-DDTHH:MM:SS.ffffffZ``."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def iso_z_from_timestamp(seconds_since_epoch: float) -> str:
    """Convert a POSIX timestamp (seconds, may be fractional) into ISO-Z.

    Used for filesystem ``st_mtime`` values surfaced via the file-listing
    routes — the frontend treats these identically to ``iso_z_now`` output.
    """
    return (
        datetime.fromtimestamp(seconds_since_epoch, timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )
