"""The read tools: everything that answers a question without changing anything.

These are reachable with a ``read`` token, which is the recommended default. A
read token cannot alter the server, so an instruction that arrives through a log
line (see the injection notes in the docs) has nothing to act on.
"""
from __future__ import annotations

from typing import Any

from fabricator_mcp.client import PanelClient
from fabricator_mcp.errors import PanelError
from fabricator_mcp.projection import (
    clamp,
    drop_empty,
    merge_hash_identification,
    project_log_lines,
    project_mod_entry,
    project_server,
    project_snapshot,
    project_version_metadata,
)

DEFAULT_LOG_LIMIT = 200
DEFAULT_SEARCH_LIMIT = 10
DEFAULT_VERSION_LIMIT = 20
MAX_METADATA_VERSIONS = 100

#: Said once, on every mods listing, because it is the one thing the listing
#: cannot show you.
MODS_LISTING_NOTE = (
    "Only jars directly in the mods folder are listed. A jar inside a subfolder "
    "is not visible here and must be managed through the panel UI."
)


def _require(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    text = value.strip()
    if "/" in text or "\\" in text:
        raise ValueError(f"{field} must not contain a path separator")
    return text


async def list_servers(client: PanelClient) -> dict[str, Any]:
    payload = await client.get("/api/servers")
    servers = payload if isinstance(payload, list) else []
    return {"servers": [project_server(record) for record in servers]}


async def get_server(client: PanelClient, server_id: str) -> dict[str, Any]:
    server_id = _require(server_id, "server_id")
    return project_server(await client.get(f"/api/servers/{server_id}"))


async def read_server_logs(
    client: PanelClient, server_id: str, limit: int = DEFAULT_LOG_LIMIT
) -> dict[str, Any]:
    server_id = _require(server_id, "server_id")
    limit = clamp(limit, 1, 1000, DEFAULT_LOG_LIMIT)
    payload = await client.get(f"/api/servers/{server_id}/logs", params={"limit": limit})
    return project_log_lines(payload, limit)


async def list_installed_mods(
    client: PanelClient, server_id: str, identify: bool = False
) -> dict[str, Any]:
    server_id = _require(server_id, "server_id")
    payload = await client.get(f"/api/servers/{server_id}/mods")
    entries = payload if isinstance(payload, list) else []
    mods = [project_mod_entry(entry) for entry in entries]

    result: dict[str, Any] = {
        "mods": mods,
        "identified": False,
        "note": MODS_LISTING_NOTE,
    }
    if not identify:
        return result

    try:
        resolved = await client.get(
            f"/api/modrinth/servers/{server_id}/resolve-installed"
        )
    except PanelError as exc:
        # Partial success is reported, never silently dropped: the list is still
        # useful, the caller just knows identification did not happen.
        result["identificationError"] = str(exc)
        return result

    payload_map = resolved.get("resolved") if isinstance(resolved, dict) else None
    result["mods"] = merge_hash_identification(mods, payload_map)
    result["identified"] = True
    return result


async def check_resource_usage(client: PanelClient, server_id: str) -> dict[str, Any]:
    server_id = _require(server_id, "server_id")
    server = await client.get(f"/api/servers/{server_id}/metrics")
    host = await client.get("/api/metrics/system")
    server = server if isinstance(server, dict) else {}
    host = host if isinstance(host, dict) else {}
    cpu = host.get("cpu") or {}
    memory = host.get("memory") or {}
    return drop_empty({
        "server": drop_empty({
            "status": server.get("status"),
            "ram": server.get("ram"),
            "pid": server.get("pid"),
        }),
        "host": drop_empty({
            "cpuPercent": cpu.get("percent"),
            "memoryPercent": memory.get("percent"),
            "memoryTotalBytes": memory.get("totalBytes"),
            "memoryUsedBytes": memory.get("usedBytes"),
        }),
    })


async def check_java(client: PanelClient, mc_version: str | None = None) -> dict[str, Any]:
    params = {"mc_version": mc_version} if mc_version else None
    status = await client.get("/api/java/status", params=params)
    installed = await client.get("/api/java/installed")
    status = status if isinstance(status, dict) else {}
    installed = installed if isinstance(installed, dict) else {}
    managed = installed.get("managed") or []
    return drop_empty({
        "requiredMajor": status.get("required_java"),
        "detectedMajor": status.get("detected_major"),
        "installed": status.get("installed"),
        "meetsRequirement": status.get("meets_requirement"),
        "enforcementSkipped": status.get("java_enforcement_skipped"),
        "managedMajors": [
            entry.get("major") for entry in managed if isinstance(entry, dict)
        ],
    })


async def list_loader_game_versions(client: PanelClient, loader: str) -> dict[str, Any]:
    """List stable Minecraft versions a Fabricator loader can install."""
    loader = _require(loader, "loader").lower()
    payload = await client.get(f"/api/loaders/{loader}/versions/game")
    versions = payload if isinstance(payload, list) else []
    return {
        "loader": loader,
        "minecraftVersions": [
            projected for version in versions[:MAX_METADATA_VERSIONS]
            if (projected := project_version_metadata(version))
        ],
    }


async def list_loader_versions(
    client: PanelClient, loader: str, mc_version: str | None = None
) -> dict[str, Any]:
    """List loader builds, optionally narrowed to one Minecraft version."""
    loader = _require(loader, "loader").lower()
    version = mc_version.strip() if isinstance(mc_version, str) and mc_version.strip() else None
    payload = await client.get(
        f"/api/loaders/{loader}/versions/loader",
        params={"mc_version": version},
    )
    versions = payload if isinstance(payload, list) else []
    return drop_empty({
        "loader": loader,
        "minecraftVersion": version,
        "versions": [
            projected for item in versions[:MAX_METADATA_VERSIONS]
            if (projected := project_version_metadata(item))
        ],
    })


async def get_backup_status(client: PanelClient, server_id: str) -> dict[str, Any]:
    """Show whether this server has usable backups and when one is next scheduled."""
    server_id = _require(server_id, "server_id")
    payload = await client.get(f"/api/servers/{server_id}/backup-summary")
    payload = payload if isinstance(payload, dict) else {}
    next_run = payload.get("next_run")
    next_run = next_run if isinstance(next_run, dict) else {}
    return drop_empty({
        "totalSnapshots": payload.get("total_snapshots"),
        "totalSizeBytes": payload.get("total_size_bytes"),
        "lastSnapshot": project_snapshot(payload.get("last_snapshot")),
        "nextRun": drop_empty({
            "configId": next_run.get("config_id"),
            "configName": next_run.get("config_name"),
            "nextRunTime": next_run.get("next_run_time"),
        }),
        "configsCount": payload.get("configs_count"),
    })


async def list_snapshots(client: PanelClient, server_id: str) -> dict[str, Any]:
    """List backup snapshots for recovery inspection; restore remains panel-UI only."""
    server_id = _require(server_id, "server_id")
    payload = await client.get(f"/api/servers/{server_id}/snapshots")
    snapshots = payload if isinstance(payload, list) else []
    return {"snapshots": [project_snapshot(snapshot) for snapshot in snapshots if isinstance(snapshot, dict)]}


async def get_install_progress(client: PanelClient, server_id: str) -> dict[str, Any]:
    server_id = _require(server_id, "server_id")
    payload = await client.get(f"/api/servers/{server_id}/install/progress")
    payload = payload if isinstance(payload, dict) else {}
    return drop_empty({
        "active": payload.get("active"),
        "phase": payload.get("phase"),
        "error": payload.get("error"),
        "bytesDone": payload.get("bytes_done"),
        "bytesTotal": payload.get("bytes_total"),
        "updatedAt": payload.get("updated_at"),
    })


#: What the panel reports when it has no release marker to read — a source
#: checkout has no .fabricator_version, only a built release does.
_UNKNOWN_VERSION = "unknown"


async def check_panel(client: PanelClient) -> dict[str, Any]:
    health = await client.get("/api/health")
    status = await client.get("/api/auth/status")
    health = health if isinstance(health, dict) else {}
    status = status if isinstance(status, dict) else {}

    result = drop_empty({
        "reachable": bool(health.get("healthy")),
        "authOk": True,  # the gate let this request through
        "managed": status.get("managed"),
        "needsSetup": status.get("needs_setup"),
    })

    # Only report a version when there is one. The panel answers "unknown" from
    # a source checkout, and older panels omit the field entirely; passing
    # either through as panelVersion reads like a version that was checked, and
    # nothing was checked. Say so instead of implying otherwise.
    raw = status.get("panel_version")
    version = raw.strip() if isinstance(raw, str) else ""
    if version and version.lower() != _UNKNOWN_VERSION:
        result["panelVersion"] = version
    else:
        result["panelVersionKnown"] = False
        result["panelVersionNote"] = (
            "This panel did not report a version, so no version check was made. "
            "A panel running from a source checkout reports none; a released "
            "build does."
        )
    return result


async def search_modrinth(
    client: PanelClient,
    query: str,
    mc_version: str | None = None,
    loader: str | None = None,
    limit: int = DEFAULT_SEARCH_LIMIT,
) -> dict[str, Any]:
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query is required")
    payload = await client.get(
        "/api/modrinth/search",
        params={
            "query": query.strip()[:128],
            "mc_version": mc_version,
            "loader": loader,
            "limit": clamp(limit, 1, 50, DEFAULT_SEARCH_LIMIT),
        },
    )
    hits = payload.get("hits") if isinstance(payload, dict) else payload
    hits = hits if isinstance(hits, list) else []
    return {
        "results": [
            drop_empty({
                "projectId": hit.get("project_id"),
                "slug": hit.get("slug"),
                "title": hit.get("title"),
                "description": hit.get("description"),
                "downloads": hit.get("downloads"),
            })
            for hit in hits
            if isinstance(hit, dict)
        ]
    }


async def get_mod_info(
    client: PanelClient, project_id: str, limit: int = DEFAULT_VERSION_LIMIT
) -> dict[str, Any]:
    project_id = _require(project_id, "project_id")
    project = await client.get(f"/api/modrinth/project/{project_id}")
    versions = await client.get(f"/api/modrinth/project/{project_id}/versions")
    project = project if isinstance(project, dict) else {}
    versions = versions if isinstance(versions, list) else []
    ceiling = clamp(limit, 1, 100, DEFAULT_VERSION_LIMIT)
    return drop_empty({
        "projectId": project.get("id"),
        "slug": project.get("slug"),
        "title": project.get("title"),
        "description": project.get("description"),
        "versions": [
            drop_empty({
                "versionId": version.get("id"),
                "versionNumber": version.get("version_number"),
                "gameVersions": version.get("game_versions"),
                "loaders": version.get("loaders"),
            })
            for version in versions[:ceiling]
            if isinstance(version, dict)
        ],
    })


async def check_mod_compatibility(
    client: PanelClient,
    project_id: str,
    mc_version: str,
    loader: str | None = None,
) -> dict[str, Any]:
    project_id = _require(project_id, "project_id")
    if not isinstance(mc_version, str) or not mc_version.strip():
        raise ValueError("mc_version is required")
    try:
        payload = await client.get(
            f"/api/modrinth/project/{project_id}/resolve-version",
            params={"mc_version": mc_version.strip(), "loader": loader},
        )
    except PanelError as exc:
        # "No suitable version found" is a 404, and it is the answer, not a fault.
        if "no suitable version" in str(exc).lower():
            return {
                "compatible": False,
                "reason": f"Modrinth has no build of {project_id} for {mc_version}"
                + (f" on {loader}" if loader else ""),
            }
        raise
    payload = payload if isinstance(payload, dict) else {}
    version = payload.get("version") or {}
    return drop_empty({
        "compatible": True,
        "versionId": version.get("id") if isinstance(version, dict) else None,
        "versionNumber": version.get("version_number") if isinstance(version, dict) else None,
    })
