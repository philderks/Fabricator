"""The manage tools: the three things that change a server.

These need a ``manage`` token. A ``read`` token still sees them advertised and
gets an honest "insufficient scope" from the panel when it calls one — the list
is not filtered by scope, because a filtered list would look like the security
boundary and it is not one.

Nothing here claims to be gated. Whether a client asks the user before calling a
tool is that client's behaviour, not something this package can promise, so
``remove_mods`` is *described* as destructive and nothing more is claimed for it.
"""
from __future__ import annotations

from typing import Any, Iterable

from fabricator_mcp.client import PanelClient
from fabricator_mcp.projection import drop_empty, project_server

ACTIONS = ("start", "stop", "restart")

MAX_FILENAMES = 50

#: Said whenever a caller reaches for a name that cannot be a delete handle.
NESTED_MOD_GUIDANCE = (
    "Mods inside a subfolder of the mods directory cannot be removed with this "
    "tool; remove them through the panel UI."
)


def _require_server_id(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("server_id is required")
    text = value.strip()
    if "/" in text or "\\" in text:
        raise ValueError("server_id must not contain a path separator")
    return text


def _clean_filenames(filenames: Any) -> list[str]:
    if isinstance(filenames, str):
        filenames = [filenames]
    if not isinstance(filenames, Iterable):
        raise ValueError("filenames must be a list of file names")

    cleaned: list[str] = []
    for raw in filenames:
        if not isinstance(raw, str) or not raw.strip():
            raise ValueError("each filename must be a non-empty string")
        name = raw.strip()
        if "/" in name or "\\" in name:
            raise ValueError(
                f"{name!r} is not a plain file name. {NESTED_MOD_GUIDANCE}"
            )
        if ".." in name:
            raise ValueError(f"{name!r} is not a plain file name")
        cleaned.append(name)

    if not cleaned:
        raise ValueError("at least one filename is required")
    if len(cleaned) > MAX_FILENAMES:
        raise ValueError(f"at most {MAX_FILENAMES} files can be removed in one call")
    return cleaned


async def control_server(client: PanelClient, server_id: str, action: str) -> dict[str, Any]:
    server_id = _require_server_id(server_id)
    if action not in ACTIONS:
        raise ValueError(f"action must be one of {', '.join(ACTIONS)}")

    payload = await client.post(f"/api/servers/{server_id}/{action}")
    payload = payload if isinstance(payload, dict) else {}
    return drop_empty({
        "success": payload.get("success"),
        "message": payload.get("message"),
        "server": project_server(payload.get("server")),
    })


async def install_server(client: PanelClient, server_id: str) -> dict[str, Any]:
    """Queue installation using the server's already persisted configuration."""
    server_id = _require_server_id(server_id)
    # No body: the panel installs the server's stored loader/version/settings.
    # In particular, this tool must not expose caller-controlled install paths
    # or modpack archives.
    payload = await client.post(f"/api/servers/{server_id}/install")
    payload = payload if isinstance(payload, dict) else {}
    return drop_empty({
        "active": payload.get("active"),
        "phase": payload.get("phase"),
        "serverId": payload.get("server_id"),
        "loader": payload.get("loader"),
        "minecraftVersion": payload.get("mc_version"),
    })


async def update_or_install_mod(
    client: PanelClient,
    server_id: str,
    project_id: str,
    mc_version: str,
    loader: str | None = None,
) -> dict[str, Any]:
    server_id = _require_server_id(server_id)
    if not isinstance(project_id, str) or not project_id.strip():
        raise ValueError("project_id is required")
    if not isinstance(mc_version, str) or not mc_version.strip():
        raise ValueError("mc_version is required")
    project_id = project_id.strip()
    if "/" in project_id or "\\" in project_id:
        raise ValueError("project_id must not contain a path separator")

    body: dict[str, Any] = {"server_id": server_id, "mc_version": mc_version.strip()}
    if loader:
        body["loader"] = loader
    # mods_folder is deliberately never sent: it is a write-location override,
    # and the panel rejects it for good reason.

    payload = await client.post(f"/api/modrinth/mod/{project_id}/install", json=body)
    payload = payload if isinstance(payload, dict) else {}
    return drop_empty({
        "success": payload.get("success"),
        "message": payload.get("message"),
        "file": payload.get("file"),
    })


async def remove_mods(
    client: PanelClient, server_id: str, filenames: Any
) -> dict[str, Any]:
    server_id = _require_server_id(server_id)
    names = _clean_filenames(filenames)

    if len(names) == 1:
        payload = await client.delete(f"/api/servers/{server_id}/mods/{names[0]}")
        payload = payload if isinstance(payload, dict) else {}
        return drop_empty({
            "success": payload.get("success"),
            "message": payload.get("message"),
            "deleted": [names[0]] if payload.get("success") else [],
        })

    payload = await client.delete(
        f"/api/servers/{server_id}/mods", json={"filenames": names}
    )
    payload = payload if isinstance(payload, dict) else {}
    return drop_empty({
        "success": payload.get("success"),
        "deleted": payload.get("deleted"),
        "errors": payload.get("errors"),
    })
