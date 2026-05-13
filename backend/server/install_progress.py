"""Per-server install progress store for loader installations.

Mirror of the modpack-install progress pattern in
``backend/modrinth/routes.py:_install_progress``, scoped to server-loader
installs (Vanilla / Fabric / Quilt / NeoForge / Forge). Modpack-install
progress lives in ``modrinth/routes.py`` and is intentionally kept
separate — different lifecycle, different keys, different UI surface.

Phase vocabulary (set by Phase 3c T2 in concrete loaders, treated as
opaque strings here):

    starting              — worker thread spawned
    resolving_versions    — versions API call in flight
    downloading_installer — subprocess installer JAR (with bytes_done/total)
    downloading_server_jar— Mojang/Fabric server JAR (with bytes_done/total)
    verifying             — SHA1 check
    running_installer     — subprocess execution; phase only, no bytes
    detecting_artifacts   — post-install file detection
    writing_eula          — final eula.txt write
    done                  — install completed successfully
    failed                — install failed (entry has 'error': <str>)

Terminal phases (``done`` / ``failed``) flip ``is_active`` to False so
the frontend's polling loop knows to stop. A missing entry also returns
False from ``is_active`` — useful when the backend restarts mid-install
and the in-memory dict is wiped.
"""
from __future__ import annotations

import threading
from typing import Any, Dict

from backend.utils.time import iso_z_now


_lock = threading.Lock()
_store: Dict[str, Dict[str, Any]] = {}

_TERMINAL_PHASES = frozenset({"done", "failed"})


def update(server_id: str, /, **kwargs: Any) -> None:
    """Merge ``kwargs`` into the entry for ``server_id``.

    ``server_id`` is positional-only so callers may also pass
    ``server_id=<value>`` as a payload kwarg without a name collision —
    useful when emitting a snapshot that mirrors the key into the body.

    Last-write-wins per key. ``updated_at`` is set on every call so the
    frontend can detect staleness. Earlier keys are preserved when not
    overwritten — e.g. ``server_id`` set on the first ``starting`` update
    survives subsequent bytes-progress updates.
    """
    timestamp = iso_z_now()
    with _lock:
        existing = _store.get(server_id) or {}
        _store[server_id] = {
            **existing,
            **kwargs,
            "updated_at": timestamp,
        }


def get(server_id: str, /) -> Dict[str, Any]:
    """Return a copy of the entry for ``server_id``, or ``{}`` if missing."""
    with _lock:
        return dict(_store.get(server_id) or {})


def clear(server_id: str, /) -> None:
    """Drop the entry for ``server_id``. No-op if missing."""
    with _lock:
        _store.pop(server_id, None)


def is_active(server_id: str, /) -> bool:
    """True iff there's an entry whose phase isn't terminal.

    Used by ``GET /api/servers/<id>/install/progress`` to tell the
    frontend whether to keep polling.
    """
    with _lock:
        entry = _store.get(server_id)
        if not entry:
            return False
        phase = entry.get("phase")
        if not phase:
            return False
        return phase not in _TERMINAL_PHASES
