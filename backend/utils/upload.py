"""Shared helpers for streamed request-body uploads.

Fabricator takes uploads as the raw request body rather than as multipart
form data (see the world-import and .mrpack-import routes), so the size cap
has to be applied *while* the body is being written: the point of a cap is
that an oversized upload never lands on disk in full.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


class UploadTooLargeError(Exception):
    """Raised when a streamed upload exceeds its configured cap."""


def env_max_bytes(var_name: str, default: int) -> int:
    """Return the byte cap from ``var_name``, or ``default``.

    Values that are not a positive integer are ignored with a warning rather
    than raising: a typo in an operator's env should not stop the app from
    booting, and the default is always a safe fallback.
    """
    raw = os.environ.get(var_name)
    if raw:
        try:
            value = int(raw)
            if value > 0:
                return value
        except (TypeError, ValueError):
            pass
        logger.warning("Ignoring invalid %s=%r", var_name, raw)
    return default


def stream_upload_to_temp(stream, dest: Path, *, max_bytes: int) -> int:
    """Stream ``stream`` to ``dest`` in chunks, capping at ``max_bytes``.

    Returns the number of bytes written. Raises :class:`UploadTooLargeError`
    (and unlinks the partial file) once the cap is exceeded, so a hostile or
    fat-fingered upload can't fill the disk.
    """
    written = 0
    chunk_size = 1024 * 1024
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(dest, "wb") as sink:
            while True:
                chunk = stream.read(chunk_size)
                if not chunk:
                    break
                written += len(chunk)
                if written > max_bytes:
                    raise UploadTooLargeError(
                        f"Upload exceeds the {max_bytes}-byte limit"
                    )
                sink.write(chunk)
    except BaseException:
        dest.unlink(missing_ok=True)
        raise
    return written
