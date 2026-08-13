"""Identify the jars in a server's mods folder against Modrinth, by hash.

The mods page needs a title and icon for every installed jar. Jars that
Fabricator installed carry that in the content manifest; jars the user dropped
in by hand (a modpack exported from the Modrinth app, a folder copied off
another server) carry nothing, and the frontend used to guess: split the
filename on ``-`` and try every prefix as a project slug, longest first. That
cost ~3.6 requests per jar — a 200-mod folder issued ~720 requests on every
page refresh, 2.4x Modrinth's 300/min budget, and still failed on any jar not
named after its slug (issue #52).

Hashing is the exact answer to the same question: ``POST /v2/version_files``
maps file hashes to the versions they belong to, in bulk. A whole mods folder
resolves in about two requests — one for the hashes, one for the project
metadata — with no misidentification possible.

Two caches keep repeat loads free:

* sha1 by (path, mtime, size) — re-listing a folder does not re-read hundreds
  of megabytes of jars.
* hash -> project id / version, held indefinitely: a file's content hash maps
  to one Modrinth version forever, so there is nothing to invalidate.
* project id -> title/icon, held with a TTL, since those can legitimately
  change.
"""
from __future__ import annotations

import hashlib
import logging
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_CHUNK_BYTES = 1024 * 1024

# Project metadata (title, icon) can change upstream; a few hours is a good
# balance between staleness and re-fetching for a page that gets refreshed a
# lot. The hash -> version mapping below needs no TTL: it is immutable.
_PROJECT_TTL_SECONDS = 6 * 3600

# Bounds on the in-memory caches. A cache that grows without limit in a
# long-lived panel process is a slow leak; these are generous enough that a
# realistic fleet never evicts.
_MAX_FILE_HASHES = 5000
_MAX_HASH_LOOKUPS = 5000
_MAX_PROJECTS = 2000

_lock = threading.Lock()
# (path, mtime_ns, size) -> sha1
_file_hash_cache: Dict[Tuple[str, int, int], str] = {}
# sha1 -> {"project_id", "version_id", "version_number"} or None for "Modrinth
# does not know this file" (a negative result worth caching just as much).
_hash_cache: Dict[str, Optional[Dict[str, Any]]] = {}
# project id -> (expires_at, {"title", "icon_url", "slug"})
_project_cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}


def clear_caches() -> None:
    """Drop every cache. Used by tests and after a bulk mods-folder change."""
    with _lock:
        _file_hash_cache.clear()
        _hash_cache.clear()
        _project_cache.clear()


def _trim(cache: dict, limit: int) -> None:
    """Evict oldest-inserted entries once `cache` exceeds `limit`.

    Insertion-ordered dicts make this FIFO rather than true LRU. Good enough:
    these caches are read-mostly and sized well above any real mods folder, so
    eviction is a safety valve rather than a hot path.
    """
    while len(cache) > limit:
        cache.pop(next(iter(cache)))


def file_sha1(path: Path) -> Optional[str]:
    """sha1 of `path`, cached on (path, mtime, size). None if unreadable."""
    try:
        stat = path.stat()
    except OSError:
        return None
    key = (str(path), stat.st_mtime_ns, stat.st_size)

    with _lock:
        cached = _file_hash_cache.get(key)
    if cached is not None:
        return cached

    hasher = hashlib.sha1()
    try:
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(_CHUNK_BYTES), b""):
                hasher.update(chunk)
    except OSError:
        return None
    digest = hasher.hexdigest()

    with _lock:
        _file_hash_cache[key] = digest
        _trim(_file_hash_cache, _MAX_FILE_HASHES)
    return digest


def _cached_versions(hashes: List[str]) -> Tuple[Dict[str, Dict[str, Any]], List[str]]:
    """Split `hashes` into already-known mappings and the ones still to fetch."""
    known: Dict[str, Dict[str, Any]] = {}
    missing: List[str] = []
    with _lock:
        for digest in hashes:
            if digest in _hash_cache:
                entry = _hash_cache[digest]
                if entry is not None:
                    known[digest] = entry
            else:
                missing.append(digest)
    return known, missing


def _store_versions(requested: List[str], found: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Cache a lookup result, including negatives, and return the positives."""
    positives: Dict[str, Dict[str, Any]] = {}
    with _lock:
        for digest in requested:
            version = found.get(digest)
            if not isinstance(version, dict):
                _hash_cache[digest] = None       # negative: don't ask again
                continue
            entry = {
                "project_id": version.get("project_id"),
                "version_id": version.get("id"),
                "version_number": version.get("version_number"),
            }
            _hash_cache[digest] = entry
            positives[digest] = entry
        _trim(_hash_cache, _MAX_HASH_LOOKUPS)
    return positives


def _cached_projects(project_ids: List[str]) -> Tuple[Dict[str, Dict[str, Any]], List[str]]:
    known: Dict[str, Dict[str, Any]] = {}
    missing: List[str] = []
    now = time.monotonic()
    with _lock:
        for pid in project_ids:
            cached = _project_cache.get(pid)
            if cached is not None and cached[0] > now:
                known[pid] = cached[1]
            else:
                missing.append(pid)
    return known, missing


def _store_projects(projects: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    stored: Dict[str, Dict[str, Any]] = {}
    expires_at = time.monotonic() + _PROJECT_TTL_SECONDS
    with _lock:
        for project in projects:
            pid = project.get("id")
            if not pid:
                continue
            entry = {
                "title": project.get("title"),
                "icon_url": project.get("icon_url"),
                "slug": project.get("slug"),
                # Side metadata, carried so the installer can ask Modrinth
                # what a jar actually is instead of guessing from its bytes
                # (see modrinth/environment.py). ``environment`` is the
                # current field; the other two are its deprecated ancestors,
                # kept as a fallback for projects not migrated yet.
                "environment": project.get("environment"),
                "client_side": project.get("client_side"),
                "server_side": project.get("server_side"),
            }
            _project_cache[pid] = (expires_at, entry)
            stored[pid] = entry
        _trim(_project_cache, _MAX_PROJECTS)
    return stored


def resolve_versions(
    client, hashes: List[str], algorithm: str = "sha1"
) -> Dict[str, Dict[str, Any]]:
    """Map file hashes to Modrinth versions, serving what the cache knows.

    Only the hashes no cache entry covers reach the network, and negatives
    are remembered too, so a folder full of hand-built jars costs one request
    the first time and none after.
    """
    wanted = list(dict.fromkeys(h for h in hashes if h))
    versions, unknown = _cached_versions(wanted)
    if unknown:
        found = client.get_versions_by_hashes(unknown, algorithm=algorithm)
        versions.update(_store_versions(unknown, found))
    return versions


def resolve_projects(client, project_ids: List[str]) -> Dict[str, Dict[str, Any]]:
    """Map project ids to cached project metadata, fetching what is missing."""
    wanted = list(dict.fromkeys(pid for pid in project_ids if pid))
    projects, unknown = _cached_projects(wanted)
    if unknown:
        projects.update(_store_projects(client.get_projects(unknown)))
    return projects


def resolve_jar_files(client, paths: List[Path]) -> Dict[str, Dict[str, Any]]:
    """Identify jars by content hash. Returns ``{filename: meta}``.

    Only files Modrinth recognises appear in the result; a jar that was
    hand-modified, repackaged, or never published there is simply absent, and
    the caller decides what to show for it.

    Costs at most two API requests per 200 unresolved jars, and zero once the
    caches are warm. ModrinthApiError propagates so the route can turn a 429
    into a retry_after the frontend already understands.
    """
    by_hash: Dict[str, List[str]] = {}
    for path in paths:
        digest = file_sha1(path)
        if digest is None:
            logger.debug("modrinth: could not hash %s", path)
            continue
        # Several files can share a hash (the same jar copied twice); they all
        # resolve to the same version.
        by_hash.setdefault(digest, []).append(path.name)

    if not by_hash:
        return {}

    versions = resolve_versions(client, list(by_hash), algorithm="sha1")
    projects = resolve_projects(
        client, [v["project_id"] for v in versions.values() if v.get("project_id")]
    )

    resolved: Dict[str, Dict[str, Any]] = {}
    for digest, filenames in by_hash.items():
        version = versions.get(digest)
        if not version:
            continue
        project = projects.get(version.get("project_id")) or {}
        meta = {
            "projectId": version.get("project_id"),
            "slug": project.get("slug"),
            "title": project.get("title"),
            "iconUrl": project.get("icon_url"),
            "versionId": version.get("version_id"),
            "versionNumber": version.get("version_number"),
        }
        for name in filenames:
            resolved[name] = meta
    return resolved
