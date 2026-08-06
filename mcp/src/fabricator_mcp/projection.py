"""Shaping what a tool hands back to the model.

THIS IS NOT A SECURITY BOUNDARY, and must never be described as one.

Credentials and host filesystem paths are removed by the panel, server-side, for
every token caller on every route, in success and error shapes alike, before a
response ever reaches this process. If everything in this module were deleted
tomorrow, no credential and no host path would be exposed.

What this module is for is context economy: an agent pays for every token it
reads, and a raw panel payload is mostly fields that answer no question anyone
asked. So we keep the fields the diagnosis loop actually uses, clamp the things
that can be unboundedly large (log lines, version lists), and drop empties.
"""
from __future__ import annotations

from typing import Any

#: A single log line longer than this is truncated; a stack trace is useful,
#: a minified 200 kB line is not.
MAX_LOG_LINE_CHARS = 2000

#: Ceiling on log lines regardless of what was asked for.
MAX_LOG_LINES = 1000


def drop_empty(payload: dict[str, Any]) -> dict[str, Any]:
    """Remove keys whose value is None or an empty mapping/sequence."""
    return {
        key: value
        for key, value in payload.items()
        if value is not None and value != {} and value != []
    }


def clamp(value: Any, low: int, high: int, default: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(low, min(number, high))


def project_server(record: Any) -> dict[str, Any]:
    """The fields that answer 'what is this server and is it running'."""
    if not isinstance(record, dict):
        return {}
    runtime = record.get("runtime")
    runtime = runtime if isinstance(runtime, dict) else {}
    return drop_empty({
        "id": record.get("id"),
        "name": record.get("name"),
        "loader": record.get("loader"),
        "version": record.get("version"),
        "loaderVersion": record.get("loaderVersion"),
        "status": record.get("status"),
        "port": record.get("port"),
        "maxPlayers": record.get("maxPlayers"),
        "runtime": drop_empty({
            "status": runtime.get("status"),
            "ram": runtime.get("ram"),
            "pid": runtime.get("pid"),
            "mods": runtime.get("mods"),
        }),
    })


def project_log_lines(payload: Any, limit: int) -> dict[str, Any]:
    """Flatten stdout/stderr into one ordered list, clamped both ways."""
    if not isinstance(payload, dict):
        return {"running": False, "lines": []}

    lines: list[dict[str, Any]] = []
    for stream in ("stdout", "stderr"):
        for entry in payload.get(stream) or []:
            if not isinstance(entry, dict):
                continue
            text = entry.get("text")
            if not isinstance(text, str):
                continue
            if len(text) > MAX_LOG_LINE_CHARS:
                text = text[:MAX_LOG_LINE_CHARS] + "… [truncated]"
            lines.append({"ts": entry.get("ts"), "stream": stream, "text": text})

    lines.sort(key=lambda item: (item.get("ts") or ""))
    ceiling = min(limit, MAX_LOG_LINES)
    return {
        "running": bool(payload.get("running")),
        "lines": lines[-ceiling:],
    }


def _modrinth_fields(source: dict[str, Any], origin: str) -> dict[str, Any]:
    return drop_empty({
        "projectId": source.get("projectId") or source.get("project_id"),
        "slug": source.get("slug"),
        "title": source.get("title"),
        "versionId": source.get("versionId") or source.get("version_id"),
        "versionNumber": source.get("versionNumber") or source.get("version_number"),
        "source": origin,
    })


def project_mod_entry(entry: Any) -> dict[str, Any]:
    """One installed jar, with an honest answer about whether it can be removed.

    ``name`` is the handle ``remove_mods`` uses. The panel lists only jars
    sitting directly in the mods folder, so in practice every listed name is a
    usable handle — but if a name ever arrives carrying a path separator it is
    not one, and the entry says so rather than letting a removal fail later.
    """
    if not isinstance(entry, dict):
        return {}
    name = entry.get("name")
    removable = bool(name) and isinstance(name, str) and "/" not in name and "\\" not in name

    projected = drop_empty({
        "name": name,
        "sizeBytes": entry.get("size"),
        "updatedAt": entry.get("updatedAt"),
    })
    projected["removable"] = removable
    if not removable:
        projected["removalNote"] = (
            "This entry is inside a subfolder of the mods directory, so it cannot "
            "be removed with remove_mods. Remove it through the panel UI."
        )

    manifest = entry.get("modrinth")
    if isinstance(manifest, dict):
        projected.update(_modrinth_fields(manifest, "manifest"))
    return projected


def merge_hash_identification(
    mods: list[dict[str, Any]], resolved: Any
) -> list[dict[str, Any]]:
    """Fill identification gaps from the content-hash lookup.

    The install manifest wins where it exists: it is what the panel actually
    did, not an inference. The hash result covers jars the panel never installed
    — the hand-dropped ones the whole feature exists for.
    """
    if not isinstance(resolved, dict):
        return mods
    for mod in mods:
        if mod.get("projectId"):
            continue
        match = resolved.get(mod.get("name"))
        if isinstance(match, dict):
            mod.update(_modrinth_fields(match, "hash"))
    return mods
