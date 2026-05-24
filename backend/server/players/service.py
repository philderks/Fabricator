"""High-level player operations.

Dispatches to:
  - running → ServerProcessRegistry.send_command (fire-and-forget)
  - stopped + addition → Mojang lookup (online-mode) or offline UUID, then file write
  - stopped + removal → name-match in file, no Mojang

The whitelist-active runtime toggle is tracked here keyed by manager identity
(via started_at) so that a stop/start cycle naturally re-initialises from the
persisted enforce-whitelist property.
"""
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from backend.server.players import files as players_files
from backend.server.players.mojang import (
    resolve_name as mojang_resolve_name,
)


WHITELIST_FILE = "whitelist.json"
OPS_FILE = "ops.json"
BANS_FILE = "banned-players.json"
BANS_IP_FILE = "banned-ips.json"


class ServerStateError(Exception):
    """The operation is not valid for the server's current state."""


class PlayerNotInList(Exception):
    """Removal target is not present in the file."""


# ----------------- helpers ------------------------------------------------

def _install_path(registry, server):
    return registry.resolve_install_path(server)


def _is_running(registry, server_id: str) -> bool:
    return registry.get_status(server_id).get("status") == "running"


def _send(registry, server_id: str, command: str) -> None:
    result = registry.send_command(server_id, command)
    if not result.get("success"):
        raise ServerStateError(result.get("message", "send_command failed"))


def _resolve_uuid_for_addition(install_path, server: Dict[str, Any], name: str) -> str:
    """For stopped-path additions only. Online-mode → Mojang; offline-mode → local."""
    online_mode = bool(server.get("onlineMode", True))
    if online_mode:
        return mojang_resolve_name(install_path, name)
    return str(players_files.offline_uuid(name))


# ----------------- whitelist ---------------------------------------------

def add_to_whitelist(registry, server, name: str) -> dict:
    server_id = str(server["id"])
    if _is_running(registry, server_id):
        _send(registry, server_id, f"whitelist add {name}")
        return {"name": name}

    install_path = _install_path(registry, server)
    uid = _resolve_uuid_for_addition(install_path, server, name)

    entries = players_files.read_json_list(install_path, WHITELIST_FILE)
    if players_files.find_entry_by_name(entries, name):
        return {"name": name}  # already there — idempotent
    entries.append({"uuid": uid, "name": name})
    players_files.write_json_list(install_path, WHITELIST_FILE, entries)
    return {"name": name, "uuid": uid}


def remove_from_whitelist(registry, server, name: str) -> dict:
    server_id = str(server["id"])
    if _is_running(registry, server_id):
        _send(registry, server_id, f"whitelist remove {name}")
        return {"name": name}

    install_path = _install_path(registry, server)
    entries = players_files.read_json_list(install_path, WHITELIST_FILE)
    entry = players_files.find_entry_by_name(entries, name)
    if not entry:
        raise PlayerNotInList(name)
    entries.remove(entry)
    players_files.write_json_list(install_path, WHITELIST_FILE, entries)
    return {"name": name}


# ----------------- ops ---------------------------------------------------

def op_player(registry, server, name: str, level: int = 4) -> dict:
    server_id = str(server["id"])
    if _is_running(registry, server_id):
        _send(registry, server_id, f"op {name}")
        return {"name": name}  # level is not applied at runtime (vanilla op takes no level)

    install_path = _install_path(registry, server)
    uid = _resolve_uuid_for_addition(install_path, server, name)
    entries = players_files.read_json_list(install_path, OPS_FILE)
    existing = players_files.find_entry_by_name(entries, name)
    if existing:
        existing["level"] = level
    else:
        entries.append({
            "uuid": uid,
            "name": name,
            "level": level,
            "bypassesPlayerLimit": False,
        })
    players_files.write_json_list(install_path, OPS_FILE, entries)
    return {"name": name, "level": level, "uuid": uid}


def deop_player(registry, server, name: str) -> dict:
    server_id = str(server["id"])
    if _is_running(registry, server_id):
        _send(registry, server_id, f"deop {name}")
        return {"name": name}

    install_path = _install_path(registry, server)
    entries = players_files.read_json_list(install_path, OPS_FILE)
    entry = players_files.find_entry_by_name(entries, name)
    if not entry:
        raise PlayerNotInList(name)
    entries.remove(entry)
    players_files.write_json_list(install_path, OPS_FILE, entries)
    return {"name": name}


# ----------------- bans --------------------------------------------------

def ban_player(registry, server, name: str, reason: Optional[str] = None) -> dict:
    server_id = str(server["id"])
    if _is_running(registry, server_id):
        command = f"ban {name}" if not reason else f"ban {name} {reason}"
        _send(registry, server_id, command)
        return {"name": name, "reason": reason}

    install_path = _install_path(registry, server)
    uid = _resolve_uuid_for_addition(install_path, server, name)
    entries = players_files.read_json_list(install_path, BANS_FILE)
    existing = players_files.find_entry_by_name(entries, name)
    payload = {
        "uuid": uid,
        "name": name,
        "created": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S %z"),
        "source": "Fabricator",
        "expires": "forever",
        "reason": reason or "Banned by an operator.",
    }
    if existing:
        existing.update(payload)
    else:
        entries.append(payload)
    players_files.write_json_list(install_path, BANS_FILE, entries)
    return {"name": name, "reason": reason, "uuid": uid}


def unban_player(registry, server, name: str) -> dict:
    server_id = str(server["id"])
    if _is_running(registry, server_id):
        _send(registry, server_id, f"pardon {name}")
        return {"name": name}

    install_path = _install_path(registry, server)
    entries = players_files.read_json_list(install_path, BANS_FILE)
    entry = players_files.find_entry_by_name(entries, name)
    if not entry:
        raise PlayerNotInList(name)
    entries.remove(entry)
    players_files.write_json_list(install_path, BANS_FILE, entries)
    return {"name": name}


# ----------------- kick (running-only) -----------------------------------

def kick_player(registry, server, name: str, reason: Optional[str] = None) -> dict:
    server_id = str(server["id"])
    if not _is_running(registry, server_id):
        raise ServerStateError("kick requires a running server")
    command = f"kick {name} {reason}" if reason else f"kick {name}"
    _send(registry, server_id, command)
    return {"name": name, "reason": reason}


# ----------------- IP bans -----------------------------------------------

def ban_ip(registry, server, ip: str, reason: Optional[str] = None) -> dict:
    server_id = str(server["id"])
    if _is_running(registry, server_id):
        command = f"ban-ip {ip}" if not reason else f"ban-ip {ip} {reason}"
        _send(registry, server_id, command)
        return {"ip": ip, "reason": reason}

    install_path = _install_path(registry, server)
    entries = players_files.read_json_list(install_path, BANS_IP_FILE)
    existing = next((e for e in entries if str(e.get("ip", "")).lower() == ip.lower()), None)
    payload = {
        "ip": ip,
        "created": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S %z"),
        "source": "Fabricator",
        "expires": "forever",
        "reason": reason or "Banned by an operator.",
    }
    if existing:
        existing.update(payload)
    else:
        entries.append(payload)
    players_files.write_json_list(install_path, BANS_IP_FILE, entries)
    return {"ip": ip, "reason": reason}


def unban_ip(registry, server, ip: str) -> dict:
    server_id = str(server["id"])
    if _is_running(registry, server_id):
        _send(registry, server_id, f"pardon-ip {ip}")
        return {"ip": ip}

    install_path = _install_path(registry, server)
    entries = players_files.read_json_list(install_path, BANS_IP_FILE)
    entry = next((e for e in entries if str(e.get("ip", "")).lower() == ip.lower()), None)
    if not entry:
        raise PlayerNotInList(ip)
    entries.remove(entry)
    players_files.write_json_list(install_path, BANS_IP_FILE, entries)
    return {"ip": ip}


# ----------------- whitelist active cache --------------------------------

class WhitelistActiveCache:
    """Per-server runtime tracking of `whitelist on/off`.

    Keyed by (server_id, startedAt) — when the server restarts, started_at
    changes and the cache miss re-initialises from the persisted
    enforce-whitelist property.
    """

    def __init__(self):
        self._records: Dict[str, Dict[str, Any]] = {}

    def _key(self, registry, server) -> Optional[float]:
        status = registry.get_status(str(server["id"]))
        if status.get("status") != "running":
            return None
        started_at = status.get("startedAt")
        return float(started_at) if started_at is not None else None

    def get(self, registry, server) -> bool:
        server_id = str(server["id"])
        started_at = self._key(registry, server)
        if started_at is None:
            # Not running — caller should display the persisted property.
            return bool(server.get("enforceWhitelist", False))
        record = self._records.get(server_id)
        if not record or record["started_at"] != started_at:
            value = bool(server.get("enforceWhitelist", False))
            self._records[server_id] = {"started_at": started_at, "active": value}
            return value
        return bool(record["active"])

    def set(self, registry, server, value: bool) -> None:
        server_id = str(server["id"])
        started_at = self._key(registry, server)
        if started_at is None:
            raise ServerStateError("Cannot set whitelist-active on a stopped server")
        self._records[server_id] = {"started_at": started_at, "active": bool(value)}


def set_whitelist_active(registry, server, cache: WhitelistActiveCache, active: bool) -> dict:
    server_id = str(server["id"])
    if not _is_running(registry, server_id):
        raise ServerStateError("whitelist on/off requires a running server")
    cache.set(registry, server, active)
    try:
        _send(registry, server_id, "whitelist on" if active else "whitelist off")
    except ServerStateError:
        cache.set(registry, server, not active)
        raise
    return {"whitelistActive": active}
