"""HTTP routes for the player-management feature."""
import logging
import re
from pathlib import Path
from typing import Optional

from flask import Blueprint, jsonify, request

from backend.server import storage
from backend.server.players import files as players_files
from backend.server.players import lastseen as players_lastseen
from backend.server.players import live as players_live
from backend.server.players import service as players_service
from backend.server.players.mojang import MojangUnavailable, PlayerNotFound
from backend.server.registry import get_server_process_registry
from backend.utils.routes import require_server, with_server_lock


logger = logging.getLogger(__name__)


players_bp = Blueprint("players", __name__, url_prefix="/api")


def _registry():
    """Lazy accessor for the process registry (mirrors the same helper in
    server/routes.py — kept local to avoid importing private helpers from
    sibling modules)."""
    return get_server_process_registry()


_NAME_RE = re.compile(r"^[A-Za-z0-9_]{1,16}$")
_IP_RE = re.compile(
    r"^"
    r"(25[0-5]|2[0-4]\d|1?\d{1,2}|\*)\."
    r"(25[0-5]|2[0-4]\d|1?\d{1,2}|\*)\."
    r"(25[0-5]|2[0-4]\d|1?\d{1,2}|\*)\."
    r"(25[0-5]|2[0-4]\d|1?\d{1,2}|\*)"
    r"$"
)
_MAX_REASON_LEN = 256


_whitelist_active_cache = players_service.WhitelistActiveCache()


def _validate_name(raw: Optional[str]):
    if not isinstance(raw, str) or not _NAME_RE.match(raw):
        return None, (
            jsonify({"error": "Invalid player name (1-16 chars, [A-Za-z0-9_])"}),
            400,
        )
    return raw, None


def _validate_reason(raw):
    if raw is None or raw == "":
        return None, None
    if not isinstance(raw, str) or any(c < " " for c in raw) or len(raw) > _MAX_REASON_LEN:
        return None, (
            jsonify({"error": f"Reason must be a single line ≤ {_MAX_REASON_LEN} chars"}),
            400,
        )
    return raw, None


def _validate_ip(raw: Optional[str]):
    if not isinstance(raw, str) or not _IP_RE.match(raw):
        return None, (
            jsonify({"error": "Invalid IP address — use IPv4 or a wildcard like 192.168.*"}),
            400,
        )
    return raw, None


def _validate_level(raw):
    try:
        level = int(raw)
    except (TypeError, ValueError):
        return None, (jsonify({"error": "Level must be an integer"}), 400)
    if not 1 <= level <= 4:
        return None, (jsonify({"error": "Level must be in 1-4"}), 400)
    return level, None


# ---------- state -----------------------------------------------------

@players_bp.route("/servers/<server_id>/players/state", methods=["GET"])
@require_server
def get_state(server_id, server):
    registry = _registry()
    install_path = registry.resolve_install_path(server)
    whitelist = players_files.read_json_list(install_path, players_service.WHITELIST_FILE)
    ops = players_files.read_json_list(install_path, players_service.OPS_FILE)
    bans = players_files.read_json_list(install_path, players_service.BANS_FILE)
    ip_bans = players_files.read_json_list(install_path, players_service.BANS_IP_FILE)
    known = players_files.read_json_list(install_path, "usercache.json")
    # Attach a real "last seen" (playerdata mtime) per known player — see
    # players/lastseen.py for why usercache.json's expiresOn is not it.
    known = players_lastseen.annotate_known_players(install_path, server, known)
    return jsonify({
        "whitelist": whitelist,
        "ops": ops,
        "bans": bans,
        "ipBans": ip_bans,
        "knownPlayers": known,
        "whitelistActive": _whitelist_active_cache.get(registry, server),
        "enforceWhitelist": bool(server.get("enforceWhitelist", False)),
        "onlineMode": bool(server.get("onlineMode", True)),
    })


@players_bp.route("/servers/<server_id>/players/online", methods=["GET"])
@require_server
def get_online(server_id, server):
    return jsonify(players_live.list_online(_registry(), server))


# ---------- whitelist -------------------------------------------------

@players_bp.route("/servers/<server_id>/players/whitelist", methods=["POST"])
@require_server
@with_server_lock
def whitelist_add(server_id, server):
    name, err = _validate_name((request.get_json() or {}).get("name"))
    if err:
        return err
    return _execute(players_service.add_to_whitelist, _registry(), server, name)


@players_bp.route("/servers/<server_id>/players/whitelist", methods=["DELETE"])
@require_server
@with_server_lock
def whitelist_remove(server_id, server):
    name, err = _validate_name((request.get_json() or {}).get("name"))
    if err:
        return err
    return _execute(players_service.remove_from_whitelist, _registry(), server, name)


@players_bp.route("/servers/<server_id>/players/whitelist/active", methods=["PATCH"])
@require_server
@with_server_lock
def whitelist_active(server_id, server):
    data = request.get_json() or {}
    active = bool(data.get("active"))
    try:
        result = players_service.set_whitelist_active(
            _registry(), server, _whitelist_active_cache, active
        )
    except players_service.ServerStateError as exc:
        return jsonify({"error": str(exc)}), 409
    return jsonify(result)


# ---------- ops -------------------------------------------------------

@players_bp.route("/servers/<server_id>/players/ops", methods=["POST"])
@require_server
@with_server_lock
def ops_add(server_id, server):
    data = request.get_json() or {}
    name, err = _validate_name(data.get("name"))
    if err:
        return err
    level, err = _validate_level(data.get("level", 4))
    if err:
        return err
    # Vanilla 'op' doesn't accept a level — level only takes effect via
    # ops.json edits while the server is stopped. Running requests with a
    # non-default level surface an explicit 409 instead of silently dropping it.
    registry = _registry()
    if registry.get_status(server_id).get("status") == "running" and level != 4:
        return jsonify({
            "error": "Op level can only be set while the server is stopped (vanilla `op` takes no level argument).",
        }), 409
    return _execute(players_service.op_player, registry, server, name, level=level)


@players_bp.route("/servers/<server_id>/players/ops", methods=["PATCH"])
@require_server
@with_server_lock
def ops_set_level(server_id, server):
    data = request.get_json() or {}
    name, err = _validate_name(data.get("name"))
    if err:
        return err
    level, err = _validate_level(data.get("level"))
    if err:
        return err
    # Vanilla has no runtime way to change op level — Minecraft only reads
    # ops.json at start. While running we 409 so the UI can show a "stop
    # server to change level" hint instead of optimistic-updating to a value
    # that won't take effect.
    registry = _registry()
    if registry.get_status(server_id).get("status") == "running":
        return jsonify({
            "error": "Op level can only be changed while the server is stopped.",
        }), 409
    return _execute(players_service.op_player, registry, server, name, level=level)


@players_bp.route("/servers/<server_id>/players/ops", methods=["DELETE"])
@require_server
@with_server_lock
def ops_remove(server_id, server):
    name, err = _validate_name((request.get_json() or {}).get("name"))
    if err:
        return err
    return _execute(players_service.deop_player, _registry(), server, name)


# ---------- bans ------------------------------------------------------

@players_bp.route("/servers/<server_id>/players/bans", methods=["POST"])
@require_server
@with_server_lock
def bans_add(server_id, server):
    data = request.get_json() or {}
    name, err = _validate_name(data.get("name"))
    if err:
        return err
    reason, err = _validate_reason(data.get("reason"))
    if err:
        return err
    return _execute(players_service.ban_player, _registry(), server, name, reason=reason)


@players_bp.route("/servers/<server_id>/players/bans", methods=["DELETE"])
@require_server
@with_server_lock
def bans_remove(server_id, server):
    name, err = _validate_name((request.get_json() or {}).get("name"))
    if err:
        return err
    return _execute(players_service.unban_player, _registry(), server, name)


# ---------- kick (running-only) --------------------------------------

@players_bp.route("/servers/<server_id>/players/kick", methods=["POST"])
@require_server
@with_server_lock
def kick(server_id, server):
    data = request.get_json() or {}
    name, err = _validate_name(data.get("name"))
    if err:
        return err
    reason, err = _validate_reason(data.get("reason"))
    if err:
        return err
    return _execute(players_service.kick_player, _registry(), server, name, reason=reason)


# ---------- IP bans ---------------------------------------------------

@players_bp.route("/servers/<server_id>/players/bans/ip", methods=["POST"])
@require_server
@with_server_lock
def ip_bans_add(server_id, server):
    data = request.get_json() or {}
    ip, err = _validate_ip(data.get("ip"))
    if err:
        return err
    reason, err = _validate_reason(data.get("reason"))
    if err:
        return err
    return _execute(players_service.ban_ip, _registry(), server, ip, reason=reason)


@players_bp.route("/servers/<server_id>/players/bans/ip", methods=["DELETE"])
@require_server
@with_server_lock
def ip_bans_remove(server_id, server):
    ip, err = _validate_ip((request.get_json() or {}).get("ip"))
    if err:
        return err
    return _execute(players_service.unban_ip, _registry(), server, ip)


# ---------- enforceWhitelist (stopped-server persisted toggle) ---------

@players_bp.route("/servers/<server_id>/players/whitelist/enforce", methods=["PATCH"])
@require_server
@with_server_lock
def whitelist_enforce(server_id, server):
    registry = _registry()
    if registry.get_status(server_id).get("status") == "running":
        return jsonify({
            "error": "Use whitelist/active to toggle the whitelist at runtime.",
        }), 409
    active = bool((request.get_json() or {}).get("active"))
    storage.update_server(server_id, {"enforceWhitelist": active})
    install_path = registry.resolve_install_path(server)
    _patch_server_property(install_path, "enforce-whitelist", active)
    return jsonify({"enforceWhitelist": active})


# ---------- helpers ---------------------------------------------------

def _patch_server_property(install_path: Path, key: str, value) -> None:
    """Update (or insert) a single key=value line in server.properties in-place."""
    str_value = str(value).lower() if isinstance(value, bool) else str(value)
    props_path = install_path / "server.properties"
    if props_path.exists():
        lines = props_path.read_text(encoding="utf-8").splitlines()
        for i, line in enumerate(lines):
            stripped = line.split("=", 1)[0].strip()
            if stripped == key:
                lines[i] = f"{key}={str_value}"
                props_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
                return
        # Key not found — append it.
        lines.append(f"{key}={str_value}")
        props_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _execute(fn, *args, **kwargs):
    try:
        return jsonify(fn(*args, **kwargs))
    except players_service.ServerStateError as exc:
        return jsonify({"error": str(exc)}), 409
    except players_service.PlayerNotInList as exc:
        return jsonify({"error": f"Player {exc} not in list"}), 404
    except PlayerNotFound as exc:
        return jsonify({"error": f"Player {exc} not found at Mojang"}), 404
    except MojangUnavailable as exc:
        return jsonify({"error": f"Could not look up player UUID — {exc}"}), 502
