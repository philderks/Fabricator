"""Managed-hosting mode: fleet-only flag + fail-closed heap-pin helpers.

These are read straight off ``os.environ`` (never ``current_app``) so the
launch-command builder and the ``run.py`` boot paths can consult them outside
any Flask application context. Off by default: a self-hoster who never sets
``FABRICATOR_MANAGED`` sees no behavioural change.
"""
from __future__ import annotations

import os

from backend.utils.strings import bool_from_str

_MANAGED_ENV = "FABRICATOR_MANAGED"
_MANAGED_MEMORY_GB_ENV = "FABRICATOR_MANAGED_MEMORY_GB"


class ManagedConfigError(Exception):
    """Managed mode is on but ``FABRICATOR_MANAGED_MEMORY_GB`` is unset/invalid.

    Raised by the launch-command builder and mapped by ``start_server`` to the
    existing clean start-failure shape (never a 500 / stacktrace).
    """


def is_managed() -> bool:
    """Return True only for an explicit truthy ``FABRICATOR_MANAGED`` (fail-safe).

    Uses the shared allowlist parser (``1/true/yes/on``, case-insensitive);
    unset / ``"0"`` / anything else keeps managed mode OFF.
    """
    return bool_from_str(os.environ.get(_MANAGED_ENV))


def managed_memory_gb() -> int | None:
    """Return the pinned per-server heap (whole GB) as a positive int, else None.

    ``None`` for unset, non-integer, zero, or negative — the fail-closed signal
    the memory pin refuses to start on. Mirrors the tolerant int-parse used for
    ``FABRICATOR_MAX_WORLD_UPLOAD_BYTES``.
    """
    raw = os.environ.get(_MANAGED_MEMORY_GB_ENV)
    if raw is None:
        return None
    try:
        gb = int(raw.strip())
    except (TypeError, ValueError):
        return None
    return gb if gb > 0 else None
