"""Read-side accessor for the online-players dict maintained by ServerManager.

The stdout-stream loop in manager.py writes OnlinePlayer entries under
ServerManager._lock. This module reads them out and optionally enriches each
with a UUID from the Mojang cache — the enrichment write happens under the
same lock to stay consistent with the existing add/discard sites.

Mojang HTTP / file-cache lookups happen *outside* the lock; only the final
attribute assignment is locked. The lock is fine-grained (microseconds), so
this keeps the stdout-stream loop unblocked even under load.
"""
from typing import Any, Dict, List

from backend.server.manager import OnlinePlayer
from backend.server.players import mojang


def list_online(registry, server: Dict[str, Any]) -> List[dict]:
    """Snapshot the server's online players as JSON-serialisable dicts."""
    server_id = str(server["id"])
    manager = registry.get_manager(server_id)
    if not manager:
        return []

    install_path = registry.resolve_install_path(server)

    # Snapshot inside the lock to avoid iteration-mid-mutation.
    with manager._lock:  # noqa: SLF001 — mirrors existing in-module locking
        snapshot = list(manager._players.values())

    # Resolve any missing UUIDs from the cache (no network) outside the lock.
    enriched: List[OnlinePlayer] = []
    for player in snapshot:
        if player.uuid is None:
            cached = mojang.lookup_cached(install_path, player.name)
            if cached:
                # Backfill under the lock so a parallel reader sees a
                # consistent UUID value.
                with manager._lock:
                    current = manager._players.get(player.name)
                    if current is not None and current.uuid is None:
                        current.uuid = cached
                        enriched.append(current)
                        continue
        enriched.append(player)

    return [
        {
            "name": p.name,
            "uuid": p.uuid,
            "joinedAt": p.joined_at.isoformat(),
        }
        for p in enriched
    ]
