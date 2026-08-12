"""Server management routes and blueprints."""
from functools import lru_cache
from pathlib import Path
import logging
import os
import shutil
import stat
import threading

from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

from backend.auth.redaction import is_token_request
from backend.modrinth import pending as pending_modpack
from backend.modrinth.client import ModrinthClient
from backend.server.manager import ServerManager
from backend.server.registry import get_server_process_registry
from backend.server import storage
from backend.server import install_progress
from backend.managed import is_managed
from backend.server.installer import (
    InstallStatus,
    get_installer_for,
    supported_loaders,
)
from backend.server.java_compat import resolve_required_java, skip_java_enforcement
from backend.server import java_manager
from backend.server import jvm_args
from backend.server.locks import get_server_lock, try_acquire, discard_lock
from backend.utils import platform as platform_utils
from backend.utils.java import parse_java_major, parse_java_version_string
from backend.utils.routes import require_server, with_server_lock
from backend.utils.time import iso_z_from_timestamp, iso_z_now

try:
    import psutil  # type: ignore
except ImportError:  # pragma: no cover - optional dependency fallback
    psutil = None

server_bp = Blueprint('server', __name__, url_prefix='/api')

# Statuses the runtime registry can authoritatively replace. Anything else
# (pending, installing, starting, stopping, failed) is owned by a route
# handler that's currently mutating the server — _augment_with_runtime must
# leave those alone or it silently downgrades 'installing' to 'stopped'
# while the install subprocess is still running, making the UI think the
# server is ready to start while the per-server lock is still held.
#
# CROSS-BRANCH CONTRACT (CC5): this set is mirrored by
# frontend/src/utils/getEffectiveStatus.js:RUNTIME_KNOWN_STATUSES. Any change
# here requires a lockstep frontend update. The pin is enforced by
# tests/test_runtime_status_pin.py.
_RUNTIME_KNOWN_STATUSES = frozenset({'running', 'stopped'})


def cleanup_stale_statuses() -> None:
    """Reset 'installing'/'starting'/'stopping' records from a previous run.

    Called once from create_app() — must tolerate a missing or malformed
    servers.json without crashing startup.
    """
    import json as _json

    stale_states = {'installing', 'starting', 'stopping'}
    try:
        servers = storage.get_all_servers()
    except (OSError, _json.JSONDecodeError):
        return

    for server in servers:
        server_id = server.get('id')
        if not server_id:
            continue
        if (server.get('status') or '').lower() in stale_states:
            try:
                storage.update_server_status(server_id, 'stopped')
            except (OSError, _json.JSONDecodeError):
                pass


def _registry():
    """Lazy accessor for the process registry."""
    return get_server_process_registry()


@lru_cache(maxsize=8)
def _loader_meta_dir(loader: str):
    """Lazy, cached accessor for a per-loader meta staging temp dir."""
    return platform_utils.temp_directory(f'fabricator-meta-{loader}')


def _handle_remove_readonly(func, path, exc_info):
    """Retry deletions on Windows by toggling the readonly bit."""
    try:
        os.chmod(path, stat.S_IWRITE)
    except OSError:
        pass
    func(path)


def _unlink_with_retry(target: Path) -> None:
    try:
        target.unlink()
    except FileNotFoundError:
        return
    except PermissionError:
        target.chmod(stat.S_IWRITE)
        target.unlink()


def _augment_with_runtime(server: dict) -> dict:
    if not server or 'id' not in server:
        return server

    runtime = dict(_registry().get_status(server['id']) or {})
    try:
        mods_path = _registry().resolve_mods_path(server)
        runtime['mods'] = sum(1 for f in mods_path.iterdir() if f.is_file() and f.suffix == '.jar')
    except Exception:
        pass

    augmented = dict(server)
    if runtime:
        augmented['runtime'] = runtime
        runtime_status = runtime.get('status')
        persisted_status = (server.get('status') or '').lower()
        if (
            runtime_status
            and runtime_status != server.get('status')
            and persisted_status in _RUNTIME_KNOWN_STATUSES
        ):
            updated = storage.update_server_status(server['id'], runtime_status)
            if updated:
                augmented = dict(updated)
                augmented['runtime'] = runtime
    return augmented


def _directory_size(path: Path) -> int:
    """Recursively sum the size of every regular file under ``path``.

    A directory's own ``st_size`` is just the inode/block size, so to report a
    meaningful folder size we walk the tree. Symlinks are skipped (to avoid
    loops and double counting) and unreadable entries are ignored.
    """
    total = 0
    try:
        with os.scandir(path) as it:
            for entry in it:
                try:
                    if entry.is_symlink():
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        total += _directory_size(Path(entry.path))
                    else:
                        total += entry.stat(follow_symlinks=False).st_size
                except OSError:
                    continue
    except OSError:
        pass
    return total


def _serialize_file_entry(path: Path, base_path: Path | None = None) -> dict:
    stat_result = path.stat()
    relative_path = path.name
    if base_path is not None:
        try:
            relative_path = str(path.relative_to(base_path))
        except ValueError:
            relative_path = path.name
    is_dir = path.is_dir()
    return {
        'name': path.name,
        'size': _directory_size(path) if is_dir else stat_result.st_size,
        'updatedAt': iso_z_from_timestamp(stat_result.st_mtime),
        'path': str(path),
        'relativePath': relative_path,
        'isDir': is_dir
    }


_SEARCH_DEFAULT_LIMIT = 200
_SEARCH_MAX_LIMIT = 500
_SEARCH_MAX_SCANNED = 200_000

# Console window served per request. The manager buffers ServerManager
# .MAX_LOG_LINES, so anything above that ceiling returns the same lines.
_LOG_DEFAULT_LIMIT = 1000
_LOG_MAX_LIMIT = ServerManager.MAX_LOG_LINES


def _serialize_search_hit(path: Path, base_path: Path) -> dict | None:
    """Directory-entry payload for a search hit.

    Deliberately not _serialize_file_entry: that computes a recursive size for
    directories, which would re-walk the tree once per matching folder. Search
    results only need enough to render a row and open the target, so folders
    report no size.
    """
    try:
        stat_result = path.stat()
        is_dir = path.is_dir()
    except OSError:
        return None

    try:
        relative_path = str(path.relative_to(base_path))
    except ValueError:
        return None

    parent = str(path.parent.relative_to(base_path)) if path.parent != base_path else ''
    return {
        'name': path.name,
        'size': None if is_dir else stat_result.st_size,
        'updatedAt': iso_z_from_timestamp(stat_result.st_mtime),
        'path': str(path),
        'relativePath': relative_path,
        'parentPath': parent,
        'isDir': is_dir,
    }


def _ensure_child_path(base: Path, child: str) -> Path:
    candidate = (base / child).resolve()
    base_resolved = base.resolve()
    try:
        candidate.relative_to(base_resolved)
    except ValueError as exc:
        raise ValueError('Invalid path') from exc
    return candidate


def _get_installer(loader: str, install_path: Path):
    """Get the appropriate installer for the given loader."""
    return get_installer_for(loader, install_path)


def _build_server_properties(server: dict) -> dict:
    level_type_value = server.get('levelType', 'default') or 'default'
    if ':' not in level_type_value:
        level_type_value = f"minecraft:{level_type_value}"

    return {
        'server-port': server.get('port', 25565),
        'server-ip': server.get('serverIp', ''),
        'motd': server.get('motd', 'A Minecraft Server'),
        'bug-report-link': server.get('bugReportLink', ''),
        'max-players': server.get('maxPlayers', 20),
        'difficulty': server.get('difficulty', 'normal'),
        'gamemode': server.get('gamemode', 'survival'),
        'force-gamemode': server.get('forceGamemode', False),
        'hardcore': server.get('hardcore', False),
        'allow-flight': server.get('allowFlight', False),
        'pvp': server.get('pvp', True),
        'spawn-protection': server.get('spawnProtection', 16),
        'function-permission-level': server.get('functionPermissionLevel', 2),
        'op-permission-level': server.get('opPermissionLevel', 4),
        'player-idle-timeout': server.get('playerIdleTimeout', 0),
        'pause-when-empty-seconds': server.get('pauseWhenEmptySeconds', 60),
        'view-distance': server.get('viewDistance', 10),
        'simulation-distance': server.get('simulationDistance', 10),
        'level-name': server.get('levelName', 'world'),
        'level-type': level_type_value,
        'level-seed': server.get('seed', ''),
        'generator-settings': server.get('generatorSettings', ''),
        'max-world-size': server.get('maxWorldSize', 29_999_984),
        'generate-structures': server.get('generateStructures', True),
        'spawn-animals': server.get('spawnAnimals', True),
        'spawn-monsters': server.get('spawnMonsters', True),
        'spawn-npcs': server.get('spawnNpcs', True),
        'entity-broadcast-range-percentage': server.get('entityBroadcastRangePercentage', 100),
        'max-chained-neighbor-updates': server.get('maxChainedNeighborUpdates', 1_000_000),
        'max-tick-time': server.get('maxTickTime', 60_000),
        'network-compression-threshold': server.get('networkCompressionThreshold', 256),
        'region-file-compression': server.get('regionFileCompression', 'deflate'),
        'sync-chunk-writes': server.get('syncChunkWrites', True),
        'use-native-transport': server.get('useNativeTransport', True),
        'online-mode': server.get('onlineMode', True),
        'enforce-secure-profile': server.get('enforceSecureProfile', True),
        'hide-online-players': server.get('hideOnlinePlayers', False),
        'prevent-proxy-connections': server.get('preventProxyConnections', False),
        'log-ips': server.get('logIps', True),
        'accepts-transfers': server.get('acceptsTransfers', False),
        'enable-status': server.get('enableStatus', True),
        'status-heartbeat-interval': server.get('statusHeartbeatInterval', 0),
        'white-list': server.get('whitelist', False),
        'enforce-whitelist': server.get('enforceWhitelist', False),
        'enable-command-block': server.get('commandBlocks', True),
        'broadcast-console-to-ops': server.get('broadcastConsoleToOps', True),
        'broadcast-rcon-to-ops': server.get('broadcastRconToOps', True),
        'enable-code-of-conduct': server.get('enableCodeOfConduct', False),
        'enable-jmx-monitoring': server.get('enableJmxMonitoring', False),
        'enable-query': server.get('enableQuery', False),
        'query.port': server.get('queryPort', server.get('port', 25565)),
        'enable-rcon': server.get('enableRcon', False),
        'rcon.port': server.get('rconPort', 25575),
        'rcon.password': server.get('rconPassword', ''),
        'rate-limit': server.get('rateLimit', 0),
        'resource-pack': server.get('resourcePack', ''),
        'resource-pack-sha1': server.get('resourcePackSha1', ''),
        'resource-pack-prompt': server.get('resourcePackPrompt', ''),
        'resource-pack-id': server.get('resourcePackId', ''),
        'require-resource-pack': server.get('requireResourcePack', False),
        'initial-enabled-packs': server.get('initialEnabledPacks', 'vanilla'),
        'initial-disabled-packs': server.get('initialDisabledPacks', ''),
        'text-filtering-config': server.get('textFilteringConfig', ''),
        'text-filtering-version': server.get('textFilteringVersion', 0),
    }


def _write_server_properties(server: dict) -> tuple[bool, str | None]:
    try:
        install_path = _registry().resolve_install_path(server)
    except ValueError as exc:
        return False, str(exc)

    properties = _build_server_properties(server)
    props_path = install_path / 'server.properties'
    lines = [
        '# Fabricator server properties',
        f'# Updated {iso_z_now()}',
    ]
    for key, value in properties.items():
        if isinstance(value, bool):
            value = str(value).lower()
        lines.append(f"{key}={value}")

    try:
        props_path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    except OSError as exc:
        return False, f'Failed to write server.properties: {exc}'

    return True, None


def _java_download_url(system: str, java_major: int) -> str:
    os_map = {'windows': 'windows', 'darwin': 'mac', 'linux': 'linux'}
    os_label = os_map.get(system)
    arch = platform_utils.arch_label()
    if not os_label:
        return f'https://adoptium.net/temurin/releases/?version={java_major}'
    return (
        f'https://api.adoptium.net/v3/binary/latest/{java_major}/ga'
        f'/{os_label}/{arch}/jre/hotspot/normal/eclipse'
    )


def _installer_type(system: str) -> str:
    return {'windows': 'msi', 'darwin': 'pkg', 'linux': 'tar.gz'}.get(system, 'installer')


def _linux_install_command(java_major: int) -> str:
    return f"sudo apt install openjdk-{java_major}-jre-headless"


def _build_java_recommendation(system: str, required_java: int) -> dict:
    return {
        'required_java': required_java,
        'download_url': _java_download_url(system, required_java),
        'linux_install_command': _linux_install_command(required_java),
        'installer_type': _installer_type(system),
        'arch': platform_utils.arch_label(),
    }


def _java_compat_payload(mc_version: str) -> dict:
    compat = resolve_required_java(mc_version)
    return compat.to_dict()


def _normalize_launch_overrides(data: dict) -> str | None:
    """Validate and normalize ``javaPath`` / ``jvmArgs`` in-place.

    Returns an error message, or None when the payload is fine. Both fields are
    user-owned launch tuning (#54): the JVM binary the server runs on, and extra
    flags appended after the installer's own. Validating on write is what keeps
    the launch builder's read path total — it must not raise, since the
    server-detail probe builds the command too.

    Empty values are normalized to "" / "" so clearing a field in the UI removes
    the override rather than persisting a blank that looks set.
    """
    for key in ('javaPath', 'jvmArgs'):
        if key not in data:
            continue
        try:
            if key == 'javaPath':
                data[key] = jvm_args.validate_java_path(data[key])
            else:
                # Stored as the raw string the user typed so the settings form
                # round-trips exactly; the launch builder re-splits it.
                raw = data[key]
                jvm_args.validate_jvm_args(raw)
                data[key] = raw.strip() if isinstance(raw, str) else raw
        except jvm_args.JvmArgsError as exc:
            return str(exc)
    return None


def _server_java_check_payload(server: dict) -> dict:
    runtime = _registry().get_java_runtime(server)
    compat = resolve_required_java(server.get('version', ''))
    detected_java = runtime.get('major_version')
    required_java = compat.required_java
    meets_requirement = (
        compat.enforceable and
        isinstance(detected_java, int) and
        detected_java >= int(required_java)
    )
    enforcement_skipped = skip_java_enforcement()
    if enforcement_skipped and compat.enforceable:
        meets_requirement = True
    return {
        'runtime': runtime,
        'compatibility': compat.to_dict(),
        'required_java': required_java,
        'detected_java': detected_java,
        'enforceable': compat.enforceable,
        'meets_requirement': bool(meets_requirement),
        'java_enforcement_skipped': enforcement_skipped,
    }


@server_bp.route('/health', methods=['GET'])
def health_check():
    return jsonify({'healthy': True})


@server_bp.route('/servers', methods=['GET'])
def get_servers():
    servers = [_augment_with_runtime(server) for server in storage.get_all_servers()]
    return jsonify(servers)


@server_bp.route('/servers', methods=['POST'])
def create_server():
    # C1 managed cap-1 lock: the only legitimate create is the first-boot
    # bootstrap while the host has zero records; every later create is refused.
    if is_managed() and storage.get_all_servers():
        return jsonify({
            'error': 'Server creation is disabled in managed mode (one server per host)'
        }), 403

    data = request.get_json()

    if not data:
        return jsonify({'error': 'Request body is required'}), 400

    required_fields = ['name', 'version', 'loader', 'port', 'installPath']
    missing_fields = [field for field in required_fields if field not in data]

    if missing_fields:
        return jsonify({
            'error': f'Missing required fields: {", ".join(missing_fields)}'
        }), 400

    requested_port = int(data.get('port', 25565))
    existing_servers = storage.get_all_servers()
    if any((server.get('port') or 25565) == requested_port for server in existing_servers):
        return jsonify({'error': f'Port {requested_port} is already in use by another server'}), 400

    # Same validation as the settings route — the create modal offers javaPath
    # too, and an unvalidated value here would produce a server that installs
    # fine and then refuses to start.
    error = _normalize_launch_overrides(data)
    if error:
        return jsonify({'error': error}), 400

    try:
        data['status'] = 'pending'
        compatibility = _java_compat_payload(data.get('version', ''))
        data['javaCompatibility'] = compatibility
        server = storage.create_server(data)
        java_check = _server_java_check_payload(server)
        recommendation = None
        if compatibility.get('required_java'):
            recommendation = _build_java_recommendation(
                platform_utils.platform_label(),
                int(compatibility['required_java'])
            )
        server['javaRequirement'] = {
            **java_check,
            'recommended_install': recommendation
        }
        return jsonify(server), 201
    except Exception as exc:
        return jsonify({'error': str(exc)}), 500


@server_bp.route('/servers/<server_id>', methods=['GET'])
@require_server
def get_server_details(server_id, server):
    return jsonify(_augment_with_runtime(server))


@server_bp.route('/servers/<server_id>/logs', methods=['GET'])
def get_server_logs(server_id):
    # type=int yields None on unparseable input, so fall back explicitly rather
    # than passing None through to the slice. Clamped to the manager's retained
    # window — a larger limit can't return more than is buffered anyway.
    limit = request.args.get('limit', default=_LOG_DEFAULT_LIMIT, type=int)
    if not limit or limit <= 0:
        limit = _LOG_DEFAULT_LIMIT
    limit = min(limit, _LOG_MAX_LIMIT)
    logs = _registry().get_logs(server_id, limit)
    return jsonify(logs)


@server_bp.route('/servers/<server_id>/files', methods=['GET'])
@require_server
def browse_server_files(server_id, server):
    relative_path = request.args.get('path', '').strip()

    try:
        base_path = _registry().resolve_install_path(server)
        target_path = _ensure_child_path(base_path, relative_path) if relative_path else base_path
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    if not target_path.exists() or not target_path.is_dir():
        return jsonify({'error': 'Directory not found'}), 404

    entries = [
        _serialize_file_entry(entry, base_path)
        for entry in target_path.iterdir()
    ]

    entries.sort(key=lambda entry: (0 if entry['isDir'] else 1, entry['name'].lower()))

    current_relative = '' if target_path == base_path else str(target_path.relative_to(base_path))
    return jsonify({
        'currentPath': current_relative,
        'absolutePath': str(target_path),
        'entries': entries,
    })


@server_bp.route('/servers/<server_id>/files/search', methods=['GET'])
@require_server
def search_server_files(server_id, server):
    query = request.args.get('q', '').strip()
    scope = request.args.get('path', '').strip()
    limit = request.args.get('limit', default=_SEARCH_DEFAULT_LIMIT, type=int)
    limit = max(1, min(limit or _SEARCH_DEFAULT_LIMIT, _SEARCH_MAX_LIMIT))

    if not query:
        return jsonify({'error': 'Query parameter q is required'}), 400

    try:
        # Resolve up front: _ensure_child_path returns a resolved path, and the
        # hits are made relative to base_path, so both sides must agree.
        base_path = _registry().resolve_install_path(server).resolve()
        root_path = _ensure_child_path(base_path, scope) if scope else base_path
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    if not root_path.exists() or not root_path.is_dir():
        return jsonify({'error': 'Directory not found'}), 404

    needle = query.lower()
    results = []
    scanned = 0
    truncated = False

    # os.walk with followlinks=False keeps symlinked directories from turning the
    # walk into a cycle. The scan cap stops a search inside a huge world folder
    # from pinning the request thread; the client is told when it fires.
    for dir_path, dir_names, file_names in os.walk(root_path, followlinks=False):
        dir_names.sort(key=str.lower)
        file_names.sort(key=str.lower)
        for name in dir_names + file_names:
            scanned += 1
            if scanned > _SEARCH_MAX_SCANNED:
                truncated = True
                break
            if needle not in name.lower():
                continue
            entry = _serialize_search_hit(Path(dir_path) / name, base_path)
            if entry is not None:
                results.append(entry)
            # Collect one past the limit so an exact-limit result set isn't
            # mislabelled as truncated.
            if len(results) > limit:
                truncated = True
                break
        if truncated:
            break

    return jsonify({
        'query': query,
        'scope': '' if root_path == base_path else str(root_path.relative_to(base_path)),
        'results': results[:limit],
        'truncated': truncated,
    })


@server_bp.route('/servers/<server_id>/files/content', methods=['GET'])
@require_server
def get_server_file_content(server_id, server):
    path_param = request.args.get('path', '').strip()
    if not path_param:
        return jsonify({'error': 'Path query parameter is required'}), 400

    try:
        base_path = _registry().resolve_install_path(server)
        target_path = _ensure_child_path(base_path, path_param)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    if not target_path.exists() or not target_path.is_file():
        return jsonify({'error': 'File not found'}), 404

    try:
        with open(target_path, 'r', encoding='utf-8') as file_handle:
            content = file_handle.read()
    except UnicodeDecodeError:
        return jsonify({'error': 'File is not UTF-8 text'}), 400

    relative_path = str(target_path.relative_to(base_path))
    return jsonify({'path': relative_path, 'content': content})


@server_bp.route('/servers/<server_id>/files/content', methods=['PUT'])
@require_server
@with_server_lock
def update_server_file_content(server_id, server):
    data = request.get_json() or {}
    path_param = (data.get('path') or '').strip()
    content = data.get('content')

    if not path_param:
        return jsonify({'error': 'Path is required'}), 400
    if content is None:
        return jsonify({'error': 'Content is required'}), 400

    try:
        base_path = _registry().resolve_install_path(server)
        target_path = _ensure_child_path(base_path, path_param)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    if not target_path.exists() or not target_path.is_file():
        return jsonify({'error': 'File not found'}), 404

    try:
        with open(target_path, 'w', encoding='utf-8') as file_handle:
            file_handle.write(content)
    except OSError as exc:
        return jsonify({'error': f'Failed to write file: {exc}'}), 500

    return jsonify({'success': True})


@server_bp.route('/servers/<server_id>/mods', methods=['GET'])
@require_server
def list_server_mods(server_id, server):
    try:
        mods_path = _registry().resolve_mods_path(server)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    # Merge in the install manifest so each jar carries the Modrinth project it
    # came from. Without it the client can only guess identity from the
    # filename, which misses whenever the jar isn't named after its slug.
    manifest = storage.get_content_manifest(server_id)

    files = []
    for path in mods_path.iterdir():
        if not path.is_file():
            continue
        entry = _serialize_file_entry(path, mods_path)
        recorded = manifest.get(path.name)
        if recorded:
            entry['modrinth'] = recorded
        files.append(entry)

    return jsonify(sorted(files, key=lambda entry: entry['name'].lower()))


@server_bp.route('/servers/<server_id>/mods/<path:filename>', methods=['DELETE'])
@require_server
def delete_server_mod(server_id, filename, server):
    try:
        mods_path = _registry().resolve_mods_path(server)
        target = _ensure_child_path(mods_path, filename)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    if not target.exists() or not target.is_file():
        return jsonify({'error': 'Mod file not found'}), 404

    _unlink_with_retry(target)
    storage.forget_content(server_id, [target.name])
    return jsonify({'success': True, 'message': f'{target.name} removed'})


@server_bp.route('/servers/<server_id>/mods', methods=['DELETE'])
@require_server
def bulk_delete_server_mods(server_id, server):
    data = request.get_json(silent=True) or {}
    filenames = data.get('filenames', [])
    if not isinstance(filenames, list) or not filenames:
        return jsonify({'error': 'filenames must be a non-empty list'}), 400

    try:
        mods_path = _registry().resolve_mods_path(server)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    deleted = []
    errors = []
    # Manifest keys are bare basenames; `filenames` may arrive as relative
    # paths, so forget by the resolved target's name rather than the input.
    forget_names = []
    for filename in filenames:
        try:
            target = _ensure_child_path(mods_path, filename)
        except ValueError as exc:
            errors.append({'filename': filename, 'error': str(exc)})
            continue
        if not target.exists() or not target.is_file():
            errors.append({'filename': filename, 'error': 'File not found'})
            continue
        _unlink_with_retry(target)
        deleted.append(filename)
        forget_names.append(target.name)

    storage.forget_content(server_id, forget_names)
    return jsonify({'success': True, 'deleted': deleted, 'errors': errors})


@server_bp.route('/servers/<server_id>/settings', methods=['PUT'])
@require_server
@with_server_lock
def update_server_settings(server_id, server):
    data = request.get_json()

    if not data:
        return jsonify({'error': 'Request body is required'}), 400

    # C2 managed reject: launch config (command / javaPath / the whole launch
    # object) is installer-owned; no legitimate settings caller sets it. Refuse
    # explicitly rather than silently strip so a managed override is loud.
    if is_managed():
        forbidden = [
            key for key in ('command', 'javaPath', 'jvmArgs', 'launch') if key in data
        ]
        if forbidden:
            return jsonify({
                'error': f"Not editable in managed mode: {', '.join(forbidden)}"
            }), 400

    # Normalize the launch-tuning fields before anything is persisted: a bad
    # value here would otherwise only surface as a server that refuses to start.
    error = _normalize_launch_overrides(data)
    if error:
        return jsonify({'error': error}), 400

    protected_fields = ['id', 'createdAt']
    for field in protected_fields:
        data.pop(field, None)

    runtime_status = _registry().get_status(server_id)
    if runtime_status.get('status') == 'running':
        return jsonify({'error': 'Stop the server before changing settings'}), 409

    server = storage.update_server(server_id, data)

    if not server:
        return jsonify({'error': 'Server not found'}), 404

    success, error_message = _write_server_properties(server)
    if not success:
        return jsonify({'error': error_message}), 500

    _registry().invalidate(server_id)

    return jsonify(server)


@server_bp.route('/servers/<server_id>/autostart', methods=['PUT'])
@require_server
def set_server_autostart(server_id, server):
    """Set the server's boot auto-start mode (always / never / last).

    This is a Fabricator-level preference, not a server.properties value, so it
    can be changed at any time — including while the server is running — and
    does not rewrite server.properties or invalidate the process manager.
    """
    from backend.server.autostart import VALID_MODES, normalize_mode

    data = request.get_json(silent=True) or {}
    mode = str(data.get('mode') or '').lower()
    if mode not in VALID_MODES:
        return jsonify({
            'error': f"mode must be one of {', '.join(sorted(VALID_MODES))}"
        }), 400

    updated = storage.update_server(server_id, {'autoStart': normalize_mode(mode)})
    if not updated:
        return jsonify({'error': 'Server not found'}), 404

    return jsonify({
        'success': True,
        'autoStart': mode,
        'server': _augment_with_runtime(updated),
    })


@server_bp.route('/servers/<server_id>', methods=['DELETE'])
@require_server
@with_server_lock
def delete_server_route(server_id, server):
    # Stop running process if needed
    _registry().stop_server(server_id)

    # Resolve install path to clean up files
    install_path = None
    try:
        install_path = _registry().resolve_install_path(server)
    except ValueError:
        install_path = None

    # Remove every scheduled backup for this server BEFORE we forget it,
    # then drop the per-server backups JSON file. Defensive: importing
    # the backups package lazily here avoids dragging APScheduler into
    # cold-import code paths that don't otherwise need it (e.g. the
    # PyInstaller bundle starting up without the scheduler enabled).
    try:
        from backend.backups import storage as backups_storage
        from backend.backups import scheduler as backups_scheduler

        for cfg in backups_storage.list_configs(server_id):
            cfg_id = cfg.get('id')
            if cfg_id:
                backups_scheduler.remove_job(cfg_id)
        backups_storage.delete_server_file(server_id)
    except Exception:
        # Backup cleanup is best-effort — never block server deletion.
        pass

    storage.delete_server(server_id)
    discard_lock(server_id)

    # Delete files on disk
    removal_error = None
    if install_path and install_path.exists():
        try:
            shutil.rmtree(install_path, onerror=_handle_remove_readonly)
        except OSError as exc:
            removal_error = str(exc)

    response = {
        'success': removal_error is None,
        'message': 'Server deleted successfully' if not removal_error else 'Server removed but files could not be deleted',
    }
    if removal_error:
        response['error'] = removal_error
    return jsonify(response), 200 if removal_error is None else 500


def _install_pending_modpack(server_id: str, install_path: Path, intent: dict) -> None:
    """Install the modpack requested at create time, once the loader is in.

    Runs inside the install worker, so there is no request in flight and
    nobody to prompt. Never raises: the loader install has already succeeded
    and the server is usable, so a pack that fails leaves a working server and
    a recorded error rather than turning the whole create into a failure.
    """
    label = pending_modpack.describe(intent)

    def _on_progress(stage='', current=0, total=0, detail=''):
        install_progress.update(
            server_id,
            phase='installing_modpack',
            modpack_name=label,
            modpack_stage=stage,
            modpack_current=current,
            modpack_total=total,
            modpack_detail=detail,
        )

    _on_progress(stage='starting')

    try:
        result = pending_modpack.install(
            ModrinthClient(), intent, install_path, _on_progress
        )
    except Exception as exc:  # noqa: BLE001 - a bad pack must not fail the server
        logger.exception('Modpack install failed for server %s', server_id)
        storage.update_server(server_id, {'pendingModpack': None})
        install_progress.update(server_id, modpack_error=str(exc))
        return

    storage.update_server(server_id, {
        'modpack': pending_modpack.modpack_record(result),
        'pendingModpack': None,
    })
    pending_modpack.cleanup(result)
    install_progress.update(
        server_id,
        modpack_installed=True,
        modpack_uncertain=len(result.get('uncertain_mod_files') or []),
        modpack_missing=len(result.get('missing_files') or []),
    )


@server_bp.route('/servers/<server_id>/install', methods=['POST'])
@require_server
def install_server(server_id, server):
    """Start the server installation asynchronously.

    Java guards are validated synchronously — failures return 400
    immediately without spawning a thread. On success the actual install
    (download + subprocess + persist) runs in a daemon thread that pushes
    phase + bytes-progress into ``install_progress``. The frontend polls
    ``GET /api/servers/<id>/install/progress`` until the phase becomes
    ``done`` or ``failed``.

    Note: this route does NOT use ``@with_server_lock`` — the worker
    thread itself acquires the per-server RLock via ``get_server_lock``
    (RLock is thread-bound, so the request thread can only probe it).
    """
    # Synchronous validation (fail-fast, no thread spawn).
    loader = (server.get('loader') or '').strip().lower()
    if not loader:
        return jsonify({'error': 'Server has no mod loader configured'}), 400
    mc_version = server.get('version')
    if not mc_version:
        return jsonify({'error': 'Server has no Minecraft version configured'}), 400

    try:
        install_path = _registry().resolve_install_path(server)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    # A modpack asked for at create time is installed by this same worker,
    # right after the loader. It used to be a second request the browser fired
    # once it saw the loader finish, which meant closing the screen or
    # refreshing lost the pack entirely (#63). Stored on the server record so
    # it is visible to anyone debugging a half-finished create.
    modpack_intent = pending_modpack.normalize_intent(
        (request.get_json(silent=True) or {}).get('modpack')
    )

    installer = _get_installer(loader, install_path)
    if not installer:
        supported = supported_loaders()
        return jsonify({
            'error': (
                f'Unsupported loader: {loader}. '
                f'Supported loaders: {", ".join(supported)}.'
            )
        }), 400

    # Detect contention synchronously: the per-server RLock is owned by
    # whichever thread currently holds it. ``try_acquire`` returns None if
    # busy. We immediately release the lock so the worker thread (a
    # different thread; RLock release is thread-bound) can acquire it
    # itself in ``_run_install``. Any racing POST in the tiny gap is
    # caught by the ``install_progress.is_active`` belt-and-braces check
    # below — once the 'starting' entry exists, racing requests get 409.
    if install_progress.is_active(server_id):
        return jsonify({'error': 'Another operation is in progress for this server'}), 409
    probe = try_acquire(server_id)
    if probe is None:
        return jsonify({'error': 'Another operation is in progress for this server'}), 409
    probe.release()

    # Write the 'starting' busy marker IMMEDIATELY after probe release,
    # BEFORE the Java guards. Closes the race window where a concurrent
    # POST during the (~70-line) Java-guard block would see is_active=False
    # AND a free lock and start a second install thread. With the marker
    # in place from here on, every failure path that returns 400 below
    # MUST call ``install_progress.clear(server_id)`` so the user's retry
    # (after fixing Java) isn't blocked by a stale 'starting' entry.
    install_progress.update(
        server_id,
        phase='starting',
        server_id=server_id,
        loader=loader,
        mc_version=mc_version,
    )

    # Java guards (synchronous — fail-fast, clear marker, return 400).
    java_check = _server_java_check_payload(server)
    compat = java_check['compatibility']
    if java_check['enforceable'] and not java_check['meets_requirement']:
        required_java = int(java_check['required_java'])
        detected_java = java_check['detected_java']
        runtime = java_check['runtime']
        install_progress.clear(server_id)
        return jsonify({
            'success': False,
            'error': (
                f'Java {required_java}+ is required for Minecraft {server.get("version")} '
                f'(detected: {detected_java if detected_java is not None else "unknown"})'
            ),
            'java_missing': bool(runtime.get('java_missing', False)),
            'java_too_old': detected_java is not None,
            'required_java': required_java,
            'detected_java': detected_java,
            'server_java_target': runtime.get('java_exec'),
            'compatibility': compat,
            'recommended_install': _build_java_recommendation(
                platform_utils.platform_label(),
                required_java
            )
        }), 400

    # Second Java guard — installers that themselves invoke java need a
    # usable JDK at install time even when the MC-compat branch above
    # didn't fire (e.g. non-enforceable older MC version that we still
    # want to allow installing for the user).
    if installer.requires_java_for_install:
        runtime = java_check['runtime']
        detected_java = java_check.get('detected_java')
        java_missing = bool(runtime.get('java_missing', False))
        required_java_raw = java_check.get('required_java')
        required_java = int(required_java_raw) if required_java_raw else None
        java_too_old = (
            detected_java is not None
            and required_java is not None
            and int(detected_java) < required_java
        )
        if java_missing or java_too_old:
            install_progress.clear(server_id)
            return jsonify({
                'success': False,
                'error': (
                    f'Java is required to install this loader. '
                    f'Detected: {detected_java if detected_java is not None else "none"}.'
                ),
                'java_missing': java_missing,
                'java_too_old': java_too_old,
                'required_java': required_java,
                'detected_java': detected_java,
                'server_java_target': runtime.get('java_exec'),
                'compatibility': compat,
                'recommended_install': _build_java_recommendation(
                    platform_utils.platform_label(),
                    required_java if required_java else 21
                )
            }), 400

    # Hand the installer the same Java the runtime path will use.
    # Default no-op for Fabric/Vanilla (they don't invoke Java);
    # NeoForge subprocess reads self.java_exec to honour managed Java
    # and per-server javaPath overrides instead of falling through to
    # whatever ``java`` happens to be on PATH.
    installer.set_java_exec(java_check['runtime'].get('java_exec'))

    # At this point we're committed to running the install. The
    # 'starting' progress entry is already in place from above; we just
    # need the persistent status flip on the server record.
    storage.update_server_status(server_id, 'installing')

    if modpack_intent:
        storage.update_server(server_id, {'pendingModpack': modpack_intent})

    # The worker thread acquires + releases the per-server lock itself
    # because RLock is thread-bound (Python's RLock binds the owning
    # thread on acquire and only that thread can release). The worker
    # uses blocking acquire so that any other operation queued in the
    # tiny race window is serialized rather than racing the install.
    def _run_install():
        worker_lock = get_server_lock(server_id)
        worker_lock.acquire()
        try:
            def _on_progress(phase, detail):
                install_progress.update(server_id, phase=phase, **detail)

            try:
                result = installer.install_with_config(
                    mc_version=mc_version,
                    server_config=server,
                    progress_callback=_on_progress,
                )
            except Exception as exc:
                storage.update_server_status(server_id, 'failed')
                install_progress.update(
                    server_id, phase='failed', error=f'Installation crashed: {exc}'
                )
                return

            if result.success:
                updates: dict = {'status': 'stopped'}
                if result.launch is not None:
                    updates['launch'] = result.launch.to_dict()
                storage.update_server(server_id, updates)
                if modpack_intent:
                    _install_pending_modpack(server_id, install_path, modpack_intent)
                # The installer already emitted 'done' before returning;
                # this update is idempotent and ensures the entry has the
                # final status flip for the frontend.
                install_progress.update(server_id, phase='done')
            else:
                storage.update_server_status(server_id, 'failed')
                install_progress.update(
                    server_id, phase='failed', error=result.message
                )
        finally:
            worker_lock.release()

    threading.Thread(
        target=_run_install,
        name=f"server-install-{server_id}",
        daemon=True,
    ).start()

    # Return current progress (includes the 'starting' entry we just inserted).
    return jsonify({
        'active': install_progress.is_active(server_id),
        **install_progress.get(server_id),
    }), 202


@server_bp.route('/servers/<server_id>/install/progress', methods=['GET'])
@require_server
def get_install_progress(server_id, server):
    """Return current install progress for the server.

    ``active`` is True iff there's an entry whose phase isn't ``done`` or
    ``failed``. Frontend polls this endpoint at ~750ms intervals until
    ``active`` flips to False.
    """
    progress = install_progress.get(server_id)
    return jsonify({
        'active': install_progress.is_active(server_id),
        **progress,
    })


@server_bp.route('/servers/<server_id>/start', methods=['POST'])
@require_server
@with_server_lock
def start_server_by_id(server_id, server):
    if server.get('status') == 'pending':
        return jsonify({
            'error': 'Server not installed yet. Call /install first.'
        }), 400

    if server.get('status') == 'installing':
        return jsonify({
            'error': 'Server is currently installing. Please wait.'
        }), 400

    compat = resolve_required_java(server.get('version', ''))
    required_java_major = compat.required_java if compat.enforceable else None
    if skip_java_enforcement():
        required_java_major = None

    try:
        result = _registry().start_server(
            server,
            required_java_major=required_java_major
        )
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    if result.get('stopping'):
        # The manager refused because a stop() is still draining (a start that
        # raced past the status snapshot above). Do NOT write status here — that
        # would clobber the persisted 'stopping' back to 'stopped' mid-drain.
        return jsonify({
            'error': result.get('message', 'Server is stopping. Please wait for it to fully stop.'),
            'server': _augment_with_runtime(server),
        }), 409

    status_value = result.get('status')
    success = status_value == 'running'
    updated_server = (
        storage.update_server_status(server_id, status_value)
        if status_value else server
    )

    response = {
        'success': success,
        'message': result.get('message', ''),
        'java_missing': result.get('java_missing', False),
        'java_too_old': result.get('java_too_old', False),
        'required_java': result.get('required_java', required_java_major),
        'detected_java': result.get('detected_java'),
        'server_java_target': result.get('server_java_target'),
        'compatibility': compat.to_dict(),
        'server': _augment_with_runtime(updated_server or server)
    }
    if required_java_major:
        response['recommended_install'] = _build_java_recommendation(
            platform_utils.platform_label(),
            int(required_java_major)
        )
    return jsonify(response), 200 if success else 400


@server_bp.route('/servers/<server_id>/stop', methods=['POST'])
@require_server
def stop_server_by_id(server_id, server):
    current_status = server.get('status')

    if current_status == 'stopping':
        return jsonify({
            'success': True,
            'message': 'Server is already stopping',
            'server': _augment_with_runtime(server),
        }), 200

    if current_status != 'running':
        result = _registry().stop_server(server_id)
        status_value = result.get('status', 'stopped')
        updated_server = storage.update_server_status(server_id, status_value) or server
        return jsonify({
            'success': True,
            'message': result.get('message', ''),
            'server': _augment_with_runtime(updated_server),
        }), 200

    updated_server = storage.update_server_status(server_id, 'stopping') or server

    def _stop_worker():
        try:
            result = _registry().stop_server(server_id)
            storage.update_server_status(server_id, result.get('status', 'stopped'))
        except Exception:
            # Never leave the persisted status stuck at 'stopping' — the manager
            # clears its own _stopping flag in stop()'s finally, so the JVM is
            # gone regardless; a stuck 'stopping' would otherwise mislead the UI.
            logger.exception("Stop worker for server %s failed", server_id)
            storage.update_server_status(server_id, 'stopped')

    threading.Thread(target=_stop_worker, daemon=True).start()

    return jsonify({
        'success': True,
        'message': 'Server is stopping',
        'server': _augment_with_runtime(updated_server),
    }), 200


@server_bp.route('/servers/<server_id>/restart', methods=['POST'])
@require_server
@with_server_lock
def restart_server_by_id(server_id, server):
    try:
        result = _registry().restart_server(server)
    except (ValueError, RuntimeError) as exc:
        return jsonify({'error': str(exc)}), 400

    start_status = result['start'].get('status')
    success = start_status == 'running'
    updated_server = (
        storage.update_server_status(server_id, start_status)
        if start_status else server
    )

    response = {
        'success': success,
        'message': result['start'].get('message', ''),
        'details': result,
        'server': _augment_with_runtime(updated_server or server)
    }
    return jsonify(response), 200 if success else 400


@server_bp.route('/java/status', methods=['GET'])
def get_java_status():
    """Return managed Java status, system Java probe and Temurin asset metadata."""
    import re
    import subprocess

    system = platform_utils.platform_label()
    mc_version = request.args.get('mc_version', '').strip()
    required_java_param = request.args.get('required_java')
    java_path_param = request.args.get('java_path') or None

    # java_path names a binary this handler then executes (``_probe`` below), so
    # honouring it for a token caller is arbitrary process execution from a READ
    # route. Rejected rather than ignored: silently probing a different binary
    # would answer a question the caller did not ask, and a hard 400 makes an
    # attempt visible instead of quietly succeeding. Session behaviour unchanged.
    if java_path_param is not None and is_token_request():
        return jsonify({
            'error': 'java_path is not accepted for token-authenticated requests'
        }), 400

    compat = resolve_required_java(mc_version) if mc_version else None
    required_java = None
    if required_java_param:
        try:
            required_java = int(required_java_param)
        except ValueError:
            required_java = None
    if required_java is None and compat and compat.required_java is not None:
        required_java = int(compat.required_java)
    if required_java is None and mc_version:
        required_java = java_manager.required_java_for(mc_version)

    def _probe(path):
        """Probe ``path -version`` — byte-same semantics as the old inline probe."""
        try:
            result = subprocess.run(
                [path, '-version'],
                capture_output=True,
                text=True,
                **platform_utils.subprocess_no_window_kwargs(),
            )
        except FileNotFoundError:
            return False, None, None
        version_output = (result.stdout or '') + (result.stderr or '')
        if result.returncode != 0:
            return False, None, None
        return (
            True,
            parse_java_version_string(version_output),
            parse_java_major(version_output),
        )

    # The flat fields mirror the binary START would use (registry
    # ``_resolve_java_exec``: explicit javaPath -> ``find_compatible_java``
    # (system-if-sufficient -> managed) -> ``'java'`` on PATH). The trailing
    # ``or 'java'`` mirrors the registry's fallback, so a present-but-too-old
    # system Java keeps being reported instead of "not installed". Without a
    # known required major there is no "effective Java" (the resolver needs a
    # major), so the probe stays the plain PATH/param probe.
    path_probe_target = java_path_param or 'java'
    java_path = path_probe_target
    if java_path_param is None and required_java is not None:
        java_path = java_manager.find_compatible_java(int(required_java)) or 'java'

    installed, version, detected_major = _probe(java_path)

    recommendation = (
        _build_java_recommendation(system, int(required_java))
        if required_java is not None else None
    )
    enforcement_skipped = skip_java_enforcement()
    meets_requirement = (
        installed and
        required_java is not None and
        detected_major is not None and
        detected_major >= required_java
    )
    if (
        enforcement_skipped and
        required_java is not None and
        installed and
        isinstance(detected_major, int)
    ):
        meets_requirement = True

    # ``system_java`` stays a PATH-only (or explicit-param) probe: when the
    # flat fields follow a managed install, this block keeps telling the PATH
    # truth. Same meets_requirement formula (incl. the enforcement-skip
    # override), applied to the PATH probe.
    if java_path == path_probe_target:
        system_installed = installed
        system_major = detected_major
        system_meets = meets_requirement
    else:
        system_installed, _, system_major = _probe(path_probe_target)
        system_meets = (
            system_installed and
            required_java is not None and
            system_major is not None and
            system_major >= required_java
        )
        if (
            enforcement_skipped and
            required_java is not None and
            system_installed and
            isinstance(system_major, int)
        ):
            system_meets = True

    system_java_block = {
        'path': path_probe_target,
        'version': system_major,
        'meets_requirement': bool(system_meets),
    }

    managed_block = None
    asset_block = None
    install_major = None
    asset_error = None
    if required_java is not None:
        managed_info = java_manager.managed_java_info(int(required_java))
        install_major = managed_info['major']
        managed_block = {
            'path': managed_info['path'],
            'installed': managed_info['installed'],
            'major': managed_info['major'],
            'substituted': managed_info['substituted'],
        }
        try:
            asset = java_manager.adoptium_asset_url(int(required_java))
            asset_block = {
                'download_url': asset['download_url'],
                'filename': asset['filename'],
                'size_bytes': asset['size_bytes'],
                'checksum_algorithm': asset['checksum_algorithm'],
                'install_major': asset['install_major'],
                'substituted': asset['substituted'],
            }
        except RuntimeError as exc:
            asset_error = str(exc)

    return jsonify({
        # New structured fields consumed by JavaInstallModal.vue
        'required_java': required_java,
        'install_major': install_major,
        'system_java': system_java_block,
        'managed_java': managed_block,
        'asset': asset_block,
        'asset_error': asset_error,
        'arch': platform_utils.arch_label(),
        # Legacy flat fields kept for backward compatibility
        'installed': installed,
        'version': version,
        'detected_major': detected_major,
        'java_path': java_path,
        'meets_requirement': meets_requirement,
        'java_enforcement_skipped': enforcement_skipped,
        'platform': system,
        'download_url': (
            asset_block['download_url'] if asset_block
            else (recommendation['download_url'] if recommendation else _java_download_url(system, 21))
        ),
        'linux_install_command': recommendation['linux_install_command'] if recommendation else _linux_install_command(21),
        'recommended_install': recommendation,
        'compatibility': compat.to_dict() if compat else None,
    })


@server_bp.route('/java/install', methods=['POST'])
def install_java_endpoint():
    """Kick off a managed Java install for the given major version."""
    data = request.get_json(silent=True) or {}
    major_raw = data.get('major')
    try:
        major = int(major_raw)
    except (TypeError, ValueError):
        return jsonify({'error': 'Field "major" must be an integer'}), 400
    if major < 8 or major > 99:
        return jsonify({'error': f'Unsupported Java major: {major}'}), 400

    task_id = java_manager.start_install_task(major)
    task = java_manager.get_install_task(task_id) or {}
    return jsonify({
        'task_id': task_id,
        'status': task.get('status', 'queued'),
        'requested_major': task.get('requested_major'),
        'install_major': task.get('install_major'),
        'substituted': task.get('substituted', False),
    })


@server_bp.route('/java/install/progress/<task_id>', methods=['GET'])
def get_java_install_progress(task_id):
    """Poll for progress of a managed Java install task."""
    task = java_manager.get_install_task(task_id)
    if not task:
        return jsonify({'error': 'Task not found'}), 404
    return jsonify(task)


@server_bp.route('/java/install/<task_id>', methods=['DELETE'])
def cancel_java_install(task_id):
    """Signal cancellation for an in-flight managed Java install task.

    Best-effort: a Python thread cannot be hard-killed, so the worker only
    notices the cancel between phases / between download chunks. The
    per-request HTTP timeout bounds how long a wedged socket can keep the
    worker alive after cancellation. Returns 404 for unknown task ids and
    409 when the task is already in a terminal state.
    """
    task = java_manager.get_install_task(task_id)
    if not task:
        return jsonify({'error': 'Task not found'}), 404
    cancelled = java_manager.cancel_install_task(task_id)
    if not cancelled:
        return jsonify({
            'error': 'Task is already in a terminal state',
            'status': task.get('status'),
        }), 409
    return jsonify(java_manager.get_install_task(task_id) or {})


@server_bp.route('/java/installed', methods=['GET'])
def list_installed_java():
    """List managed Java runtimes plus the system Java probe.

    Used by the Java manager in the Settings tab to render installed
    runtimes. Managed entries are removable; the system entry is informational
    only (lives outside Fabricator's data directory).
    """
    return jsonify({
        'managed': java_manager.list_installed_java(),
        'system': java_manager.system_java_info(),
    })


@server_bp.route('/java/installed/<int:major>', methods=['DELETE'])
def uninstall_installed_java(major):
    """Remove a managed Java runtime by major version.

    Returns 404 when no managed install exists for ``major``. Removal is safe:
    if a server later needs the removed runtime, the normal resolution flow
    re-triggers the install prompt on next start.
    """
    try:
        removed = java_manager.uninstall_java(major)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    if not removed:
        return jsonify({'error': f'No managed Java {major} install found'}), 404
    return jsonify({'success': True, 'major': major})


@server_bp.route('/metrics/system', methods=['GET'])
def get_system_metrics():
    if not psutil:
        return jsonify({'error': 'System metrics are unavailable'}), 500

    cpu_percent = psutil.cpu_percent(interval=0.1)
    memory = psutil.virtual_memory()
    return jsonify({
        'cpu': {
            'percent': round(cpu_percent, 1)
        },
        'memory': {
            'percent': round(memory.percent, 1),
            'totalBytes': memory.total,
            'usedBytes': memory.used
        }
    })


@server_bp.route('/servers/<server_id>/metrics', methods=['GET'])
@require_server
def get_server_metrics(server_id, server):
    """Get performance metrics for a specific server."""
    runtime = _registry().get_status(server_id) or {}

    metrics = {
        'status': runtime.get('status', 'stopped'),
        'ram': runtime.get('ram'),
        'pid': runtime.get('pid'),
    }

    return jsonify(metrics)


def _validated_loader(loader):
    """Return the normalised loader name, or None when it is not a known loader.

    Called BEFORE anything builds a path out of ``loader``: the metadata staging
    directory is named after this value and created with ``mkdir(parents=True)``,
    and creating a directory from an unvalidated request path segment is wrong
    regardless of who asked. Validated against the same LOADER_REGISTRY that
    ``get_installer_for`` resolves against, so the two can never disagree.
    """
    normalised = (loader or '').strip().lower()
    if normalised not in supported_loaders():
        return None
    return normalised


@server_bp.route('/loaders/<loader>/versions/game', methods=['GET'])
def get_loader_game_versions(loader):
    """Return Minecraft versions supported by ``loader``."""
    normalised = _validated_loader(loader)
    if normalised is None:
        return jsonify({'error': f'Unknown loader: {loader}'}), 404
    installer = _get_installer(normalised, _loader_meta_dir(normalised))
    if installer is None:
        return jsonify({'error': f'Unknown loader: {loader}'}), 404
    return jsonify(installer.get_minecraft_versions())


@server_bp.route('/loaders/<loader>/versions/loader', methods=['GET'])
def get_loader_loader_versions(loader):
    """Return loader-specific versions for ``loader``.

    Some loaders (e.g. Vanilla) do not have a separate loader version; those
    return an empty list.
    """
    normalised = _validated_loader(loader)
    if normalised is None:
        return jsonify({'error': f'Unknown loader: {loader}'}), 404
    installer = _get_installer(normalised, _loader_meta_dir(normalised))
    if installer is None:
        return jsonify({'error': f'Unknown loader: {loader}'}), 404
    mc_version = request.args.get('mc_version')
    return jsonify(installer.get_available_versions(mc_version))


@server_bp.route('/servers/<server_id>/console', methods=['POST'])
@require_server
def send_console_command(server_id, server):
    data = request.get_json() or {}
    command = (data.get('command') or '').strip()

    if not command:
        return jsonify({'error': 'Command is required'}), 400

    result = _registry().send_command(server_id, command)
    status_code = 200 if result.get('success') else 400
    return jsonify(result), status_code
