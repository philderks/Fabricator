"""JSON-backed storage for backup configs and snapshot history.

One file per server at ``<BACKUPS_DIR>/<server_id>.json``. This keeps
blast radius small if one file corrupts, makes server-delete cleanup a
single ``unlink``, and lets concurrent backups of two different servers
write to different files (and different per-server locks) without
serialising on a single global storage lock.

File shape::

    {
      "configs": [
        {
          "id": "bkc_...",
          "serverId": "srv_...",
          "name": "Daily",
          "storagePath": "/path/to/archives",
          "maxSnapshots": 7,
          "flush": true,
          "shutdown": false,
          "compress": true,
          "exclusions": ["logs/**"],
          "schedule": {
            "enabled": true,
            "frequencyHours": 24,
            "timeOfDay": "03:00",
            "timezone": "Europe/Amsterdam"
          },
          "createdAt": "...",
          "updatedAt": "..."
        }
      ],
      "snapshots": [
        {
          "id": "snp_...",
          "configId": "bkc_...",
          "serverId": "srv_...",
          "type": "backup|safety|restore",
          "createdAt": "...",
          "filePath": "...",
          "fileName": "...",
          "sizeBytes": 0,
          "durationSeconds": 0.0,
          "status": "success|warning|error",
          "message": "...",
          "sourceSnapshotId": "snp_... | null",
          "safetySnapshotId": "snp_... | null",
          "mode": "in_place|reset|null"
        }
      ]
    }

Atomic writes mirror :mod:`backend.server.storage` — tmp file + fsync +
``os.replace``. Concurrency uses one ``threading.RLock`` per server id;
two backups of two different servers don't block each other.
"""
from __future__ import annotations

import json
import os
import threading
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from backend.core.config import get_config
from backend.server import storage as server_storage
from backend.server.registry import get_server_process_registry
from backend.utils.time import iso_z_now


# Per-server-id RLock map. Two servers' backups never serialise on each
# other; the same server's backup + a snapshot-record update do.
_storage_locks: Dict[str, threading.RLock] = {}
_storage_locks_guard = threading.Lock()

# In-memory lookup cache: config_id -> server_id and snapshot_id -> server_id.
# Invalidated on every create/delete; cold walk over `<BACKUPS_DIR>/*.json`
# is cheap (tens of servers at most).
_lookup_cache: Dict[str, str] = {}
_lookup_cache_guard = threading.Lock()


def _resolve_backups_dir() -> Path:
    """Resolve ``BACKUPS_DIR`` from current env state (not cached)."""
    config = get_config()
    return Path(getattr(config, "BACKUPS_DIR", "")).expanduser()


def _resolve_backups_file(server_id: str) -> Path:
    """Return ``<BACKUPS_DIR>/<server_id>.json`` for the given server id."""
    return _resolve_backups_dir() / f"{server_id}.json"


def _get_server_lock(server_id: str) -> threading.RLock:
    """Return (creating if needed) the per-server-id storage RLock."""
    with _storage_locks_guard:
        lock = _storage_locks.get(server_id)
        if lock is None:
            lock = threading.RLock()
            _storage_locks[server_id] = lock
        return lock


def _invalidate_lookup_cache() -> None:
    with _lookup_cache_guard:
        _lookup_cache.clear()


def _empty_doc() -> Dict[str, Any]:
    return {"configs": [], "snapshots": []}


def _read_file(server_id: str) -> Dict[str, Any]:
    """Read the per-server JSON file. Missing → empty doc."""
    path = _resolve_backups_file(server_id)
    if not path.exists():
        return _empty_doc()
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        return _empty_doc()
    data.setdefault("configs", [])
    data.setdefault("snapshots", [])
    return data


def _write_file(server_id: str, data: Dict[str, Any]) -> None:
    """Atomically write ``data`` to ``<BACKUPS_DIR>/<server_id>.json``."""
    target = _resolve_backups_file(server_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, target)
    except Exception:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _generate_config_id() -> str:
    return f"bkc_{uuid.uuid4().hex[:10]}"


def _generate_snapshot_id() -> str:
    return f"snp_{uuid.uuid4().hex[:10]}"


# ---------------------------------------------------------------------------
# Configs
# ---------------------------------------------------------------------------


def list_configs(server_id: str) -> List[Dict[str, Any]]:
    """Return all backup configs for ``server_id`` (copy, safe to mutate)."""
    with _get_server_lock(server_id):
        doc = _read_file(server_id)
        return [dict(cfg) for cfg in doc["configs"]]


def get_config_record(server_id: str, config_id: str) -> Optional[Dict[str, Any]]:
    """Return the config dict for ``config_id`` under ``server_id``, or None."""
    with _get_server_lock(server_id):
        doc = _read_file(server_id)
        for cfg in doc["configs"]:
            if cfg.get("id") == config_id:
                return dict(cfg)
    return None


def _normalise_config_payload(data: Dict[str, Any]) -> Dict[str, Any]:
    """Coerce/default the user-provided config fields without inventing data."""
    out: Dict[str, Any] = {}
    if "name" in data:
        out["name"] = str(data.get("name") or "Backup")
    if "storagePath" in data:
        out["storagePath"] = str(data.get("storagePath") or "")
    if "maxSnapshots" in data:
        try:
            out["maxSnapshots"] = max(0, int(data.get("maxSnapshots") or 0))
        except (TypeError, ValueError):
            out["maxSnapshots"] = 0
    if "flush" in data:
        out["flush"] = bool(data.get("flush"))
    if "shutdown" in data:
        out["shutdown"] = bool(data.get("shutdown"))
    if "compress" in data:
        out["compress"] = bool(data.get("compress"))
    if "exclusions" in data:
        exclusions = data.get("exclusions") or []
        if isinstance(exclusions, list):
            out["exclusions"] = [str(item) for item in exclusions if item]
        else:
            out["exclusions"] = []
    if "schedule" in data and isinstance(data.get("schedule"), dict):
        sched = data["schedule"]
        out["schedule"] = {
            "enabled": bool(sched.get("enabled", False)),
            "frequencyHours": int(sched.get("frequencyHours") or 24),
            "timeOfDay": str(sched.get("timeOfDay") or "03:00"),
            # IANA zone the user's browser reported; empty means "fall back to
            # the host zone" (the scheduler resolves it — see _resolve_timezone).
            "timezone": str(sched.get("timezone") or "").strip(),
        }
    return out


def create_config(server_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Append a new backup config under ``server_id`` and return it."""
    normalised = _normalise_config_payload(data)
    now = iso_z_now()
    record: Dict[str, Any] = {
        "id": _generate_config_id(),
        "serverId": server_id,
        "name": "Backup",
        "storagePath": "",
        "maxSnapshots": 0,
        "flush": True,
        "shutdown": False,
        "compress": True,
        "exclusions": [],
        "schedule": {
            "enabled": False,
            "frequencyHours": 24,
            "timeOfDay": "03:00",
            "timezone": "",
        },
        **normalised,
        "createdAt": now,
        "updatedAt": now,
    }
    with _get_server_lock(server_id):
        doc = _read_file(server_id)
        doc["configs"].append(record)
        _write_file(server_id, doc)
    _invalidate_lookup_cache()
    return dict(record)


def update_config(
    server_id: str, config_id: str, data: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    """Merge ``data`` into the config record. Returns the updated record."""
    normalised = _normalise_config_payload(data)
    with _get_server_lock(server_id):
        doc = _read_file(server_id)
        for cfg in doc["configs"]:
            if cfg.get("id") == config_id:
                cfg.update(normalised)
                cfg["updatedAt"] = iso_z_now()
                _write_file(server_id, doc)
                _invalidate_lookup_cache()
                return dict(cfg)
    return None


def delete_config(
    server_id: str, config_id: str
) -> Optional[Tuple[Dict[str, Any], List[Dict[str, Any]]]]:
    """Remove the config and any associated snapshot records.

    Returns ``(config, snapshots)`` for the removed records, or ``None`` if
    the config did not exist. The caller decides whether to unlink the
    actual archive files (the snapshots' ``filePath``) — purging files is
    NEVER a silent default; see ``backend.backups.routes`` for the explicit
    purge UX.
    """
    with _get_server_lock(server_id):
        doc = _read_file(server_id)
        removed_config: Optional[Dict[str, Any]] = None
        kept_configs: List[Dict[str, Any]] = []
        for cfg in doc["configs"]:
            if cfg.get("id") == config_id and removed_config is None:
                removed_config = dict(cfg)
                continue
            kept_configs.append(cfg)
        if removed_config is None:
            return None

        removed_snapshots: List[Dict[str, Any]] = []
        kept_snapshots: List[Dict[str, Any]] = []
        for snap in doc["snapshots"]:
            if snap.get("configId") == config_id:
                removed_snapshots.append(dict(snap))
            else:
                kept_snapshots.append(snap)

        doc["configs"] = kept_configs
        doc["snapshots"] = kept_snapshots
        _write_file(server_id, doc)
    _invalidate_lookup_cache()
    return removed_config, removed_snapshots


# ---------------------------------------------------------------------------
# Snapshots
# ---------------------------------------------------------------------------


def list_snapshots(
    server_id: str, config_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Return snapshot records under ``server_id``.

    Filtered by ``config_id`` when provided. Sorted newest-first by
    ``createdAt`` for caller convenience (the route layer presents the
    UI's history table directly from this list).
    """
    with _get_server_lock(server_id):
        doc = _read_file(server_id)
        snaps = list(doc["snapshots"])
    if config_id is not None:
        snaps = [s for s in snaps if s.get("configId") == config_id]
    snaps.sort(key=lambda s: s.get("createdAt", ""), reverse=True)
    return [dict(s) for s in snaps]


def get_snapshot(server_id: str, snapshot_id: str) -> Optional[Dict[str, Any]]:
    """Return the snapshot record for ``snapshot_id`` under ``server_id``."""
    with _get_server_lock(server_id):
        doc = _read_file(server_id)
        for snap in doc["snapshots"]:
            if snap.get("id") == snapshot_id:
                return dict(snap)
    return None


def record_snapshot(server_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Append a snapshot record under ``server_id`` and return it.

    Mandatory fields the caller must supply: ``configId``, ``type``,
    ``filePath`` (str). Missing fields are left as ``None`` rather than
    invented — callers always know what they wrote to disk.
    """
    now = iso_z_now()
    record: Dict[str, Any] = {
        "id": data.get("id") or _generate_snapshot_id(),
        "configId": data.get("configId"),
        "serverId": server_id,
        "type": data.get("type") or "backup",
        "createdAt": data.get("createdAt") or now,
        "filePath": data.get("filePath"),
        "fileName": data.get("fileName"),
        "sizeBytes": data.get("sizeBytes"),
        "durationSeconds": data.get("durationSeconds"),
        "status": data.get("status") or "success",
        "message": data.get("message"),
        "sourceSnapshotId": data.get("sourceSnapshotId"),
        "safetySnapshotId": data.get("safetySnapshotId"),
        "mode": data.get("mode"),
    }
    with _get_server_lock(server_id):
        doc = _read_file(server_id)
        doc["snapshots"].append(record)
        _write_file(server_id, doc)
    _invalidate_lookup_cache()
    return dict(record)


def delete_snapshot_record(server_id: str, snapshot_id: str) -> bool:
    """Drop the snapshot record. Returns True iff something was removed."""
    with _get_server_lock(server_id):
        doc = _read_file(server_id)
        before = len(doc["snapshots"])
        doc["snapshots"] = [
            s for s in doc["snapshots"] if s.get("id") != snapshot_id
        ]
        removed = len(doc["snapshots"]) < before
        if removed:
            _write_file(server_id, doc)
            _invalidate_lookup_cache()
        return removed


def delete_server_file(server_id: str) -> bool:
    """Remove ``<BACKUPS_DIR>/<server_id>.json``. Called on server delete."""
    path = _resolve_backups_file(server_id)
    try:
        path.unlink()
    except FileNotFoundError:
        return False
    finally:
        _invalidate_lookup_cache()
    return True


# ---------------------------------------------------------------------------
# Lookup helpers (config_id / snapshot_id → server_id)
# ---------------------------------------------------------------------------


def _walk_and_cache() -> None:
    """Rebuild the in-memory lookup cache by walking all per-server files.

    Run under the cache guard. Number of servers is tens at most, so even
    a cold walk is cheap. Called by ``lookup_server_for_config`` /
    ``lookup_server_for_snapshot`` when a key isn't in the cache.
    """
    backups_dir = _resolve_backups_dir()
    if not backups_dir.exists():
        return
    for path in backups_dir.glob("*.json"):
        server_id = path.stem
        try:
            with open(path, "r", encoding="utf-8") as fh:
                doc = json.load(fh)
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(doc, dict):
            continue
        for cfg in doc.get("configs") or []:
            cid = cfg.get("id")
            if cid:
                _lookup_cache[cid] = server_id
        for snap in doc.get("snapshots") or []:
            sid = snap.get("id")
            if sid:
                _lookup_cache[sid] = server_id


def lookup_server_for_config(config_id: str) -> Optional[str]:
    """Return the owning ``server_id`` for ``config_id`` (or None)."""
    with _lookup_cache_guard:
        hit = _lookup_cache.get(config_id)
        if hit is not None:
            return hit
        _walk_and_cache()
        return _lookup_cache.get(config_id)


def lookup_server_for_snapshot(snapshot_id: str) -> Optional[str]:
    """Return the owning ``server_id`` for ``snapshot_id`` (or None)."""
    with _lookup_cache_guard:
        hit = _lookup_cache.get(snapshot_id)
        if hit is not None:
            return hit
        _walk_and_cache()
        return _lookup_cache.get(snapshot_id)


def all_configs() -> List[Dict[str, Any]]:
    """Return every config across every server. Used by the scheduler init."""
    backups_dir = _resolve_backups_dir()
    if not backups_dir.exists():
        return []
    results: List[Dict[str, Any]] = []
    for path in backups_dir.glob("*.json"):
        server_id = path.stem
        try:
            doc = _read_file(server_id)
        except (OSError, json.JSONDecodeError):
            continue
        for cfg in doc.get("configs") or []:
            results.append(dict(cfg))
    return results


def resolve_config_storage_path(cfg: Dict[str, Any]) -> Path:
    """Return the resolved storage ``Path`` for a backup config.

    Empty or missing ``storagePath`` → ``<install_path>/backups``.
    """
    raw = (cfg.get("storagePath") or "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    sid = cfg.get("serverId")
    server = server_storage.get_server(sid) if sid else None
    if server:
        install_path = get_server_process_registry().resolve_install_path(server)
        return install_path / "backups"
    raise ValueError("Config has no storagePath and no resolvable serverId")


def reset_for_tests() -> None:
    """Clear module-level caches and per-server locks (tests only)."""
    with _storage_locks_guard:
        _storage_locks.clear()
    _invalidate_lookup_cache()
