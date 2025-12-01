"""Server management routes and blueprints."""
from datetime import datetime
from pathlib import Path
import shutil
import zipfile

from flask import Blueprint, jsonify, request

from backend.server.registry import get_server_process_registry
from backend.server import storage
from backend.server.manager import ServerManager
from backend.server.installer import FabricInstaller, InstallStatus

server_bp = Blueprint('server', __name__, url_prefix='/api')
server_manager = ServerManager()
process_registry = get_server_process_registry()


def _augment_with_runtime(server: dict) -> dict:
    if not server or 'id' not in server:
        return server

    runtime = process_registry.get_status(server['id'])
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
    if not str(candidate).startswith(str(base_resolved)):
        raise ValueError('Invalid path')
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


@server_bp.route('/status', methods=['GET'])
def get_status():
    status = server_manager.status()
    status.update({"version": "1.0.0"})
    return jsonify(status)


@server_bp.route('/start', methods=['POST'])
def start_server_legacy():
    result = server_manager.start()
    return jsonify(result)


@server_bp.route('/stop', methods=['POST'])
def stop_server_legacy():
    result = server_manager.stop()
    return jsonify(result)


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

    try:
        data['status'] = 'pending'
        server = storage.create_server(data)
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

    target.unlink()
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
            archive_path.unlink(missing_ok=True)
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
    backup_path = backups_dir / f'{backup_id}.zip'
    if not backup_path.exists():
        return jsonify({'error': 'Backup not found'}), 404

    try:
        for entry in base_path.iterdir():
            if entry == backups_dir:
                continue
            if entry.is_dir():
                shutil.rmtree(entry)
            else:
                entry.unlink()

        with zipfile.ZipFile(backup_path, 'r') as zip_file:
            _safe_extract_zip(zip_file, base_path)
    except OSError as exc:
        return jsonify({'error': f'Failed to restore backup: {exc}'}), 500
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    return jsonify({'success': True, 'message': 'Backup restored successfully'})


@server_bp.route('/servers/<server_id>/settings', methods=['PUT'])
def update_server_settings(server_id):
    data = request.get_json()

    if not data:
        return jsonify({'error': 'Request body is required'}), 400

    protected_fields = ['id', 'createdAt']
    for field in protected_fields:
        data.pop(field, None)

    server = storage.update_server(server_id, data)

    if not server:
        return jsonify({'error': 'Server not found'}), 404

    return jsonify(server)


@server_bp.route('/servers/<server_id>', methods=['DELETE'])
def delete_server_route(server_id):
    success = storage.delete_server(server_id)

    if not success:
        return jsonify({'error': 'Server not found'}), 404

    return jsonify({
        'success': True,
        'message': 'Server deleted successfully'
    })


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

    try:
        result = process_registry.start_server(server)
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
        'server': _augment_with_runtime(updated_server or server)
    }
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


@server_bp.route('/fabric/versions/game', methods=['GET'])
def get_fabric_game_versions():
    """Get Minecraft versions supported by Fabric."""
    installer = FabricInstaller(Path('/tmp'))
    versions = installer.get_minecraft_versions()
    return jsonify(versions)


@server_bp.route('/fabric/versions/loader', methods=['GET'])
def get_fabric_loader_versions():
    """Get available Fabric loader versions."""
    mc_version = request.args.get('mc_version')
    installer = FabricInstaller(Path('/tmp'))
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