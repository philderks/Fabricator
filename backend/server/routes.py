"""Server management routes and blueprints."""
from datetime import datetime
from pathlib import Path
import os
import shutil
import stat
import zipfile

from flask import Blueprint, jsonify, request

from backend.server.registry import get_server_process_registry
from backend.server import storage
from backend.server.installer import FabricInstaller, InstallStatus
from backend.server.java_compat import resolve_required_java, skip_java_enforcement
from backend.utils import platform as platform_utils

try:
    import psutil  # type: ignore
except ImportError:  # pragma: no cover - optional dependency fallback
    psutil = None

server_bp = Blueprint('server', __name__, url_prefix='/api')
process_registry = get_server_process_registry()
FABRIC_META_STAGING_DIR = platform_utils.temp_directory('fabricator-meta')


def _cleanup_stale_statuses() -> None:
    stale_states = {'installing', 'starting', 'stopping'}
    for server in storage.get_all_servers():
        server_id = server.get('id')
        if not server_id:
            continue
        if (server.get('status') or '').lower() in stale_states:
            storage.update_server_status(server_id, 'stopped')


_cleanup_stale_statuses()


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

    runtime = dict(process_registry.get_status(server['id']) or {})
    try:
        mods_path = process_registry.resolve_mods_path(server)
        runtime['mods'] = sum(1 for f in mods_path.iterdir() if f.is_file() and f.suffix == '.jar')
    except Exception:
        pass

    augmented = dict(server)
    if runtime:
        augmented['runtime'] = runtime
        runtime_status = runtime.get('status')
        if runtime_status and runtime_status != server.get('status'):
            updated = storage.update_server_status(server['id'], runtime_status)
            if updated:
                augmented = dict(updated)
                augmented['runtime'] = runtime
    return augmented


def _serialize_file_entry(path: Path, base_path: Path | None = None) -> dict:
    stat_result = path.stat()
    relative_path = path.name
    if base_path is not None:
        try:
            relative_path = str(path.relative_to(base_path))
        except ValueError:
            relative_path = path.name
    return {
        'name': path.name,
        'size': stat_result.st_size,
        'updatedAt': datetime.utcfromtimestamp(stat_result.st_mtime).isoformat() + 'Z',
        'path': str(path),
        'relativePath': relative_path,
        'isDir': path.is_dir()
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
    loader = loader.lower()
    if loader == 'fabric':
        return FabricInstaller(install_path)
    return None


def _get_install_path(server: dict) -> Path:
    try:
        return process_registry._resolve_install_path(server)
    except ValueError as exc:
        raise ValueError(str(exc)) from exc


def _get_backups_dir(base_path: Path) -> Path:
    backups_dir = base_path / 'backups'
    backups_dir.mkdir(parents=True, exist_ok=True)
    return backups_dir


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
        install_path = _get_install_path(server)
    except ValueError as exc:
        return False, str(exc)

    properties = _build_server_properties(server)
    props_path = install_path / 'server.properties'
    lines = [
        '# Fabricator server properties',
        f'# Updated {datetime.utcnow().isoformat()}Z'
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


def _safe_extract_zip(zip_file: zipfile.ZipFile, destination: Path) -> None:
    destination = destination.resolve()

    for member in zip_file.infolist():
        member_path = destination / member.filename
        resolved_path = member_path.resolve()
        if not str(resolved_path).startswith(str(destination)):
            raise ValueError('Archive contains invalid paths')

        if member.is_dir():
            resolved_path.mkdir(parents=True, exist_ok=True)
            continue

        resolved_path.parent.mkdir(parents=True, exist_ok=True)
        with zip_file.open(member, 'r') as source, open(resolved_path, 'wb') as target:
            shutil.copyfileobj(source, target)


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


def _server_java_check_payload(server: dict) -> dict:
    runtime = process_registry.get_java_runtime(server)
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


@server_bp.route('/status', methods=['GET'])
def get_status():
    return jsonify({
        'error': 'Deprecated endpoint. Use /api/servers/<id>/metrics or other new routes.'
    }), 410


@server_bp.route('/start', methods=['POST'])
def start_server_legacy():
    return jsonify({
        'error': 'Deprecated endpoint. Use /api/servers/<server_id>/start instead.'
    }), 410


@server_bp.route('/stop', methods=['POST'])
def stop_server_legacy():
    return jsonify({
        'error': 'Deprecated endpoint. Use /api/servers/<server_id>/stop instead.'
    }), 410


@server_bp.route('/health', methods=['GET'])
def health_check():
    return jsonify({'healthy': True})


@server_bp.route('/servers', methods=['GET'])
def get_servers():
    servers = [_augment_with_runtime(server) for server in storage.get_all_servers()]
    return jsonify(servers)


@server_bp.route('/servers', methods=['POST'])
def create_server():
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
def get_server_details(server_id):
    server = storage.get_server(server_id)

    if not server:
        return jsonify({'error': 'Server not found'}), 404

    return jsonify(_augment_with_runtime(server))


@server_bp.route('/servers/<server_id>/logs', methods=['GET'])
def get_server_logs(server_id):
    limit = request.args.get('limit', default=200, type=int)
    logs = process_registry.get_logs(server_id, limit)
    return jsonify(logs)


@server_bp.route('/servers/<server_id>/files', methods=['GET'])
def browse_server_files(server_id):
    server = storage.get_server(server_id)
    if not server:
        return jsonify({'error': 'Server not found'}), 404

    relative_path = request.args.get('path', '').strip()

    try:
        base_path = _get_install_path(server)
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
    return jsonify({'currentPath': current_relative, 'entries': entries})


@server_bp.route('/servers/<server_id>/files/content', methods=['GET'])
def get_server_file_content(server_id):
    path_param = request.args.get('path', '').strip()
    if not path_param:
        return jsonify({'error': 'Path query parameter is required'}), 400

    server = storage.get_server(server_id)
    if not server:
        return jsonify({'error': 'Server not found'}), 404

    try:
        base_path = _get_install_path(server)
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
def update_server_file_content(server_id):
    data = request.get_json() or {}
    path_param = (data.get('path') or '').strip()
    content = data.get('content')

    if not path_param:
        return jsonify({'error': 'Path is required'}), 400
    if content is None:
        return jsonify({'error': 'Content is required'}), 400

    server = storage.get_server(server_id)
    if not server:
        return jsonify({'error': 'Server not found'}), 404

    try:
        base_path = _get_install_path(server)
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
def list_server_mods(server_id):
    server = storage.get_server(server_id)
    if not server:
        return jsonify({'error': 'Server not found'}), 404

    try:
        mods_path = process_registry.resolve_mods_path(server)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    files = [
        _serialize_file_entry(path, mods_path)
        for path in mods_path.iterdir()
        if path.is_file()
    ]
    return jsonify(sorted(files, key=lambda entry: entry['name'].lower()))


@server_bp.route('/servers/<server_id>/mods/<path:filename>', methods=['DELETE'])
def delete_server_mod(server_id, filename):
    server = storage.get_server(server_id)
    if not server:
        return jsonify({'error': 'Server not found'}), 404

    try:
        mods_path = process_registry.resolve_mods_path(server)
        target = _ensure_child_path(mods_path, filename)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    if not target.exists() or not target.is_file():
        return jsonify({'error': 'Mod file not found'}), 404

    _unlink_with_retry(target)
    return jsonify({'success': True, 'message': f'{target.name} removed'})


@server_bp.route('/servers/<server_id>/backups', methods=['GET'])
def list_server_backups(server_id):
    server = storage.get_server(server_id)
    if not server:
        return jsonify({'error': 'Server not found'}), 404

    try:
        base_path = _get_install_path(server)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    backups_dir = _get_backups_dir(base_path)
    backups = [
        _serialize_file_entry(path, backups_dir)
        for path in backups_dir.glob('*.zip')
    ]
    backups.sort(key=lambda entry: entry['updatedAt'], reverse=True)
    return jsonify(backups)


@server_bp.route('/servers/<server_id>/backup', methods=['POST'])
def create_server_backup(server_id):
    server = storage.get_server(server_id)
    if not server:
        return jsonify({'error': 'Server not found'}), 404

    runtime_status = process_registry.get_status(server_id)
    if runtime_status.get('status') == 'running':
        return jsonify({'error': 'Stop the server before creating a backup to avoid data corruption'}), 400

    try:
        base_path = _get_install_path(server)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    backups_dir = _get_backups_dir(base_path)
    timestamp = datetime.utcnow().strftime('%Y%m%d-%H%M%S')
    archive_path = backups_dir / f'{timestamp}.zip'

    try:
        with zipfile.ZipFile(archive_path, 'w', compression=zipfile.ZIP_DEFLATED) as zip_file:
            for file_path in base_path.rglob('*'):
                if backups_dir in file_path.parents or file_path == backups_dir:
                    continue
                if file_path.is_dir():
                    continue
                zip_file.write(file_path, file_path.relative_to(base_path))
    except OSError as exc:
        if archive_path.exists():
            try:
                _unlink_with_retry(archive_path)
            except OSError:
                pass
        return jsonify({'error': f'Failed to create backup: {exc}'}), 500

    return jsonify({
        'success': True,
        'backup': _serialize_file_entry(archive_path, backups_dir)
    })


@server_bp.route('/servers/<server_id>/backups/<backup_id>/restore', methods=['POST'])
def restore_server_backup(server_id, backup_id):
    server = storage.get_server(server_id)
    if not server:
        return jsonify({'error': 'Server not found'}), 404

    try:
        base_path = _get_install_path(server)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    status = process_registry.get_status(server_id)
    if status.get('status') == 'running':
        return jsonify({'error': 'Stop the server before restoring a backup'}), 400

    backups_dir = _get_backups_dir(base_path)
    try:
        backup_path = _ensure_child_path(backups_dir, f'{backup_id}.zip')
    except ValueError:
        return jsonify({'error': 'Invalid backup ID'}), 400

    if not backup_path.exists():
        return jsonify({'error': 'Backup not found'}), 404

    try:
        for entry in base_path.iterdir():
            if entry == backups_dir:
                continue
            if entry.is_dir():
                shutil.rmtree(entry, onerror=_handle_remove_readonly)
            else:
                _unlink_with_retry(entry)

        with zipfile.ZipFile(backup_path, 'r') as zip_file:
            _safe_extract_zip(zip_file, base_path)
    except OSError as exc:
        return jsonify({'error': f'Failed to restore backup: {exc}'}), 500
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    return jsonify({'success': True, 'message': 'Backup restored successfully'})


@server_bp.route('/servers/<server_id>/backups/<backup_id>', methods=['DELETE'])
def delete_server_backup(server_id, backup_id):
    server = storage.get_server(server_id)
    if not server:
        return jsonify({'error': 'Server not found'}), 404

    try:
        base_path = _get_install_path(server)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    backups_dir = _get_backups_dir(base_path)
    try:
        backup_path = _ensure_child_path(backups_dir, f'{backup_id}.zip')
    except ValueError:
        return jsonify({'error': 'Invalid backup ID'}), 400

    if not backup_path.exists():
        return jsonify({'error': 'Backup not found'}), 404

    try:
        _unlink_with_retry(backup_path)
    except OSError as exc:
        return jsonify({'error': f'Failed to delete backup: {exc}'}), 500

    return jsonify({'success': True, 'message': 'Backup deleted successfully'})


@server_bp.route('/servers/<server_id>/settings', methods=['PUT'])
def update_server_settings(server_id):
    data = request.get_json()

    if not data:
        return jsonify({'error': 'Request body is required'}), 400

    protected_fields = ['id', 'createdAt']
    for field in protected_fields:
        data.pop(field, None)

    server = storage.get_server(server_id)

    if not server:
        return jsonify({'error': 'Server not found'}), 404

    runtime_status = process_registry.get_status(server_id)
    if runtime_status.get('status') == 'running':
        return jsonify({'error': 'Stop the server before changing settings'}), 409

    server = storage.update_server(server_id, data)

    if not server:
        return jsonify({'error': 'Server not found'}), 404

    success, error_message = _write_server_properties(server)
    if not success:
        return jsonify({'error': error_message}), 500

    process_registry.invalidate(server_id)

    return jsonify(server)


@server_bp.route('/servers/<server_id>', methods=['DELETE'])
def delete_server_route(server_id):
    server = storage.get_server(server_id)
    if not server:
        return jsonify({'error': 'Server not found'}), 404

    # Stop running process if needed
    process_registry.stop_server(server_id)

    # Resolve install path to clean up files
    install_path = None
    try:
        install_path = _get_install_path(server)
    except ValueError:
        install_path = None

    # Remove server from storage
    storage.delete_server(server_id)

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


@server_bp.route('/servers/<server_id>/install', methods=['POST'])
def install_server(server_id):
    """Install the server (download JAR, configure, etc.)."""
    server = storage.get_server(server_id)
    if not server:
        return jsonify({'error': 'Server not found'}), 404

    loader = (server.get('loader') or '').strip().lower()
    if not loader:
        return jsonify({'error': 'Server has no mod loader configured'}), 400
    mc_version = server.get('version')

    if not mc_version:
        return jsonify({'error': 'Server has no Minecraft version configured'}), 400

    try:
        install_path = process_registry._resolve_install_path(server)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    installer = _get_installer(loader, install_path)
    if not installer:
        supported_loaders = ['fabric']
        return jsonify({
            'error': (
                f'Unsupported loader: {loader}. '
                f'Supported loaders: {", ".join(supported_loaders)}.'
            )
        }), 400

    storage.update_server_status(server_id, 'installing')

    try:
        java_check = _server_java_check_payload(server)
        compat = java_check['compatibility']
        if java_check['enforceable'] and not java_check['meets_requirement']:
            required_java = int(java_check['required_java'])
            detected_java = java_check['detected_java']
            runtime = java_check['runtime']
            storage.update_server_status(server_id, 'stopped')
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

        result = installer.install_with_config(
            mc_version=mc_version,
            server_config=server
        )

        if result.success:
            storage.update_server_status(server_id, 'stopped')
            return jsonify({
                'success': True,
                'message': result.message,
                'details': result.details,
                'server': _augment_with_runtime(storage.get_server(server_id))
            })
        else:
            storage.update_server_status(server_id, 'failed')
            return jsonify({
                'success': False,
                'message': result.message,
                'details': result.details
            }), 500

    except Exception as exc:
        storage.update_server_status(server_id, 'failed')
        return jsonify({
            'success': False,
            'message': f'Installation failed: {str(exc)}'
        }), 500


@server_bp.route('/servers/<server_id>/start', methods=['POST'])
def start_server_by_id(server_id):
    server = storage.get_server(server_id)
    if not server:
        return jsonify({'error': 'Server not found'}), 404

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
        result = process_registry.start_server(
            server,
            required_java_major=required_java_major
        )
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

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
def stop_server_by_id(server_id):
    server = storage.get_server(server_id)
    if not server:
        return jsonify({'error': 'Server not found'}), 404

    result = process_registry.stop_server(server_id)
    status_value = result.get('status')
    success = status_value == 'stopped'
    updated_server = (
        storage.update_server_status(server_id, status_value)
        if status_value else server
    )

    response = {
        'success': success,
        'message': result.get('message', ''),
        'server': _augment_with_runtime(updated_server or server)
    }
    return jsonify(response), 200 if success else 400


@server_bp.route('/servers/<server_id>/restart', methods=['POST'])
def restart_server_by_id(server_id):
    server = storage.get_server(server_id)
    if not server:
        return jsonify({'error': 'Server not found'}), 404

    try:
        result = process_registry.restart_server(server)
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
    """Check Java installation status and return platform-appropriate download URL."""
    import subprocess
    import re

    system = platform_utils.platform_label()
    mc_version = request.args.get('mc_version', '').strip()
    required_java_param = request.args.get('required_java')
    java_path = request.args.get('java_path') or 'java'

    compat = resolve_required_java(mc_version) if mc_version else None
    required_java = None
    if required_java_param:
        try:
            required_java = int(required_java_param)
        except ValueError:
            required_java = None
    if required_java is None and compat and compat.required_java is not None:
        required_java = int(compat.required_java)

    try:
        result = subprocess.run([java_path, '-version'], capture_output=True, text=True)
        version_output = (result.stdout or '') + (result.stderr or '')
        installed = result.returncode == 0
        version = None
        detected_major = None
        if installed:
            match = re.search(r'version "([^"]+)"', version_output)
            if match:
                version = match.group(1)
                if version.startswith('1.'):
                    parts = version.split('.')
                    if len(parts) > 1 and parts[1].isdigit():
                        detected_major = int(parts[1])
                else:
                    major_match = re.match(r'^(\d+)', version)
                    if major_match:
                        detected_major = int(major_match.group(1))
    except FileNotFoundError:
        installed = False
        version = None
        detected_major = None

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
    return jsonify({
        'installed': installed,
        'version': version,
        'detected_major': detected_major,
        'java_path': java_path,
        'required_java': required_java,
        'meets_requirement': meets_requirement,
        'java_enforcement_skipped': enforcement_skipped,
        'platform': system,
        'download_url': recommendation['download_url'] if recommendation else _java_download_url(system, 21),
        'linux_install_command': recommendation['linux_install_command'] if recommendation else _linux_install_command(21),
        'recommended_install': recommendation,
        'compatibility': compat.to_dict() if compat else None,
    })


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
def get_server_metrics(server_id):
    """Get performance metrics for a specific server."""
    server = storage.get_server(server_id)
    if not server:
        return jsonify({'error': 'Server not found'}), 404

    runtime = process_registry.get_status(server_id) or {}

    metrics = {
        'status': runtime.get('status', 'stopped'),
        'ram': runtime.get('ram'),
        'pid': runtime.get('pid'),
    }

    return jsonify(metrics)


@server_bp.route('/fabric/versions/game', methods=['GET'])
def get_fabric_game_versions():
    """Get Minecraft versions supported by Fabric."""
    installer = FabricInstaller(FABRIC_META_STAGING_DIR)
    versions = installer.get_minecraft_versions()
    return jsonify(versions)


@server_bp.route('/fabric/versions/loader', methods=['GET'])
def get_fabric_loader_versions():
    """Get available Fabric loader versions."""
    mc_version = request.args.get('mc_version')
    installer = FabricInstaller(FABRIC_META_STAGING_DIR)
    versions = installer.get_available_versions(mc_version)
    return jsonify(versions)


@server_bp.route('/servers/<server_id>/console', methods=['POST'])
def send_console_command(server_id):
    data = request.get_json() or {}
    command = (data.get('command') or '').strip()

    if not command:
        return jsonify({'error': 'Command is required'}), 400

    server = storage.get_server(server_id)
    if not server:
        return jsonify({'error': 'Server not found'}), 404

    result = process_registry.send_command(server_id, command)
    status_code = 200 if result.get('success') else 400
    return jsonify(result), status_code