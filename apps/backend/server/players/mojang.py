"""Mojang Name→UUID lookups with on-disk cache.

Used only on the stopped-path addition flow and read-only by live.py for
online-player UUID enrichment. The running path passes names to Minecraft
commands directly — no Mojang call.
"""
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional, Union

import requests

from backend.server.players import files as players_files


logger = logging.getLogger(__name__)


MOJANG_PROFILE_URL = "https://api.mojang.com/profiles/minecraft"
_CACHE_PATH = ".fabricator/uuid-cache.json"
_TIMEOUT = (5, 10)  # (connect, read) seconds
_BATCH_LIMIT = 10


class MojangUnavailable(Exception):
    """Raised when Mojang's API can't be reached or returns an unexpected status."""


class PlayerNotFound(Exception):
    """Raised when Mojang's API returns no profile for a name."""


def _load_cache(server_dir: Path) -> Dict[str, dict]:
    raw = players_files.read_json_list(server_dir, _CACHE_PATH)
    # File-on-disk is a dict but we store via the json-list helper, so we
    # keep the canonical form here as list[{name, uuid, fetched_at}]
    # and reshape into a lookup dict on load.
    return {str(entry["name"]).lower(): entry for entry in raw if "name" in entry}


def _save_cache(server_dir: Path, cache: Dict[str, dict]) -> None:
    players_files.write_json_list(server_dir, _CACHE_PATH, list(cache.values()))


def _format_uuid(raw_id: str) -> str:
    """Convert Mojang's dashless 32-char hex to canonical 8-4-4-4-12 UUID."""
    return f"{raw_id[0:8]}-{raw_id[8:12]}-{raw_id[12:16]}-{raw_id[16:20]}-{raw_id[20:]}"


def resolve_name(server_dir: Union[str, Path], name: str) -> str:
    """Look up the UUID for `name`. Cache-first.

    Raises MojangUnavailable / PlayerNotFound. Returns the canonical
    8-4-4-4-12 dashed UUID string.
    """
    server_dir = Path(server_dir)
    cache = _load_cache(server_dir)
    cached = cache.get(name.lower())
    if cached and "uuid" in cached:
        return cached["uuid"]

    try:
        response = requests.post(
            MOJANG_PROFILE_URL,
            json=[name],
            timeout=_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise MojangUnavailable(str(exc)) from exc

    if response.status_code != 200:
        raise MojangUnavailable(
            f"Mojang API returned HTTP {response.status_code}"
        )

    profiles = response.json()
    if not profiles:
        raise PlayerNotFound(name)

    profile = profiles[0]
    raw_id = profile.get("id")
    canonical_name = profile.get("name", name)
    if not raw_id:
        raise MojangUnavailable("Mojang profile is missing 'id'")

    formatted = _format_uuid(raw_id)

    cache[canonical_name.lower()] = {
        "name": canonical_name,
        "uuid": formatted,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }
    _save_cache(server_dir, cache)

    return formatted


def lookup_cached(server_dir: Union[str, Path], name: str) -> Optional[str]:
    """Cache-only lookup, no network. Used by live.py for non-blocking UUID enrichment."""
    cache = _load_cache(Path(server_dir))
    cached = cache.get(name.lower())
    return cached.get("uuid") if cached else None
