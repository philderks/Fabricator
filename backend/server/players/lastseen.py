"""Derive each known player's "last seen" from their playerdata file mtime.

Minecraft persists a player's ``<uuid>.dat`` under ``<world>/playerdata`` on
quit, on autosave while online, and on ``/save-all`` — so the file's mtime
tracks the last time the player was actually online. That is a far more
faithful "last seen" than ``usercache.json``'s ``expiresOn``, which is a
30-day cache TTL: it also advances on admin name-lookups (whitelist/op/ban of
a never-joined player on a running server) and never moves on logout.

Scope: the ``level-name`` reader here exists ONLY for this last-seen path. It
is deliberately not wired into the backup code's world-dir model
(``backups.service._level_dirs``) — reconciling those is a separate issue.
"""
import logging
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from backend.utils.time import iso_z_from_timestamp


logger = logging.getLogger(__name__)

_DEFAULT_LEVEL_NAME = "world"

# Canonical 8-4-4-4-12 UUID. usercache.json is written by Minecraft (trusted),
# but this value is interpolated into a filesystem path, so we refuse anything
# that isn't a plain dashed UUID — a stray path separator or ``..`` must never
# reach ``stat()``.
_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def read_level_name(install_path: Path, server: Dict[str, Any]) -> str:
    """Resolve the active world folder name.

    Prefers the on-disk ``level-name`` from ``server.properties`` (the value
    Minecraft actually uses); falls back to the stored ``levelName`` config
    field, then ``"world"``. Blank/whitespace values are treated as absent.
    """
    from_props = _level_name_from_properties(install_path)
    if from_props:
        return from_props
    configured = str(server.get("levelName") or "").strip()
    return configured or _DEFAULT_LEVEL_NAME


def _level_name_from_properties(install_path: Path) -> Optional[str]:
    """Return the ``level-name`` value from ``server.properties``, or None.

    A minimal single-key reader — intentionally not a general properties
    parser. Skips comments/blank lines; the last assignment wins, mirroring
    Minecraft's top-to-bottom read into a map.
    """
    props = install_path / "server.properties"
    try:
        text = props.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    value: Optional[str] = None
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, raw = stripped.partition("=")
        if key.strip() == "level-name":
            value = raw.strip()
    return value or None


def last_seen_iso(install_path: Path, level_name: str, uuid: str) -> Optional[str]:
    """Newest per-player-file mtime for ``uuid`` as an ISO-Z string, or None.

    Minecraft has stored per-player data at two locations across versions, so
    we probe both — no version detection, no version-string parsing:

      * ``<level>/playerdata/<uuid>.dat``     — classic layout (through 26.0)
      * ``<level>/players/data/<uuid>.dat``   — the 26.1 save-format overhaul,
        which also nested dimensions under ``dimensions/<ns>/<dim>/`` and moved
        stats/advancements under ``players/`` (verified live on a 26.2 server:
        the ``.dat`` mtime equals the player's disconnect time).

    For each layout we also consider ``.dat_old``. NOTE: ``.dat_old`` is an
    UNVERIFIED, defensive fallback — a single observed session only ever
    produced ``.dat``; the ``.dat`` → ``.dat_old`` rotation was not observed,
    so its exact semantics here rest on Minecraft's documented save-swap, not
    on a captured artifact.

    We take the newest mtime across every candidate that exists (rather than
    first-hit) so a world upgraded across the 26.1 boundary — both layouts
    present on disk — reports its most recent activity, not a stale legacy
    file. Returns None when the uuid is malformed or no candidate exists;
    None is a valid "never seen" state (e.g. a player still in their very
    first session has no file yet, and the live path shows them as online).
    """
    if not _UUID_RE.match(uuid or ""):
        return None
    world = install_path / level_name
    candidates = (
        world / "players" / "data" / f"{uuid}.dat",
        world / "players" / "data" / f"{uuid}.dat_old",
        world / "playerdata" / f"{uuid}.dat",
        world / "playerdata" / f"{uuid}.dat_old",
    )
    mtimes = []
    for candidate in candidates:
        try:
            mtimes.append(candidate.stat().st_mtime)
        except OSError:
            continue
    if not mtimes:
        return None
    return iso_z_from_timestamp(max(mtimes))


def annotate_known_players(
    install_path: Path,
    server: Dict[str, Any],
    known: Iterable[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Return knownPlayers entries each augmented with a ``lastSeen`` field.

    ``lastSeen`` is an ISO-8601 (``...Z``) string derived from the player's
    playerdata mtime, or None when no playerdata exists (e.g. a player who was
    whitelisted/opped by name but never joined). Entries are shallow-copied so
    the on-disk usercache list is never mutated.
    """
    level_name = read_level_name(install_path, server)
    result: List[Dict[str, Any]] = []
    for entry in known:
        augmented = dict(entry)
        augmented["lastSeen"] = last_seen_iso(
            install_path, level_name, str(entry.get("uuid") or "")
        )
        result.append(augmented)
    return result
