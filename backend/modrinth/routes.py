"""Modrinth API routes."""
import inspect
import os
import zipfile
from datetime import datetime
from pathlib import Path

from flask import Blueprint, current_app, jsonify, request

from backend.modrinth.client import ModrinthClient, ModrinthApiError
from backend.server import storage
from backend.server.registry import get_server_process_registry

modrinth_bp = Blueprint('modrinth', __name__, url_prefix='/api/modrinth')
modrinth_client = ModrinthClient()
process_registry = get_server_process_registry()


def _modrinth_error_response(exc: ModrinthApiError):
    status = exc.status_code or 502
    payload = {'error': str(exc)}
    details = getattr(exc, 'details', None)
    if isinstance(details, dict):
        payload.update(details)
    return jsonify(payload), status


def _parse_bool(value, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in ('1', 'true', 'yes', 'on')
    return default


def _create_server_backup(install_path: Path) -> str:
    backups_dir = install_path / 'backups'
    backups_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.utcnow().strftime('%Y%m%d-%H%M%S')
    backup_name = f"modpack-switch-{stamp}.zip"
    backup_path = backups_dir / backup_name

    with zipfile.ZipFile(backup_path, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for path in install_path.rglob('*'):
            if path == backup_path:
                continue
            try:
                rel = path.relative_to(install_path)
            except ValueError:
                continue
            if rel.parts and rel.parts[0] == 'backups':
                continue
            archive.write(path, rel)

    return backup_name


def _resolve_mods_folder(server_id: str | None):
    if server_id:
        server = storage.get_server(server_id)
        if not server:
            return None, ({'error': 'Server not found'}, 404)
        try:
            path = process_registry.resolve_mods_path(server)
            return path, None
        except ValueError as exc:
            return None, ({'error': str(exc)}, 400)

    legacy_root = Path(os.path.join(os.getcwd(), 'server'))
    mods_path = legacy_root / 'mods'
    mods_path.mkdir(parents=True, exist_ok=True)
    return mods_path, None


@modrinth_bp.route('/search', methods=['GET'])
def search_mods():
    query = request.args.get('query', '')
    mc_version = request.args.get('mc_version')
    loader = request.args.get('loader')
    try:
        limit = int(request.args.get('limit', 20))
    except (TypeError, ValueError):
        limit = 20
    try:
        offset = int(request.args.get('offset', 0))
    except (TypeError, ValueError):
        offset = 0
    index = request.args.get('index', 'downloads')

    try:
        result = modrinth_client.search_mods(
            query=query,
            mc_version=mc_version,
            loader=loader,
            limit=limit,
            offset=offset,
            index=index
        )
        return jsonify(result)
    except ModrinthApiError as exc:
        return _modrinth_error_response(exc)


@modrinth_bp.route('/modpacks/search', methods=['GET'])
def search_modpacks():
    query = request.args.get('query', '')
    mc_version = request.args.get('mc_version')
    loader = request.args.get('loader')
    strict_version = request.args.get('strict_version', 'false').lower() in ('true', '1', 'yes')
    try:
        limit = int(request.args.get('limit', 20))
    except (TypeError, ValueError):
        limit = 20
    try:
        offset = int(request.args.get('offset', 0))
    except (TypeError, ValueError):
        offset = 0
    index = request.args.get('index', 'downloads')

    try:
        result = modrinth_client.search_modpacks(
            query=query,
            mc_version=mc_version,
            loader=loader,
            limit=limit,
            offset=offset,
            index=index
        )

        # If strict version filtering returns no hits, retry without mc_version.
        # This keeps UX friendly for modpacks that are compatible but not tagged consistently.
        hits = result.get('hits') if isinstance(result, dict) else None
        if mc_version and not strict_version and isinstance(hits, list) and not hits:
            fallback = modrinth_client.search_modpacks(
                query=query,
                mc_version=None,
                loader=loader,
                limit=limit,
                offset=offset,
                index=index
            )
            if isinstance(fallback, dict):
                fallback['version_filter_fallback'] = True
            return jsonify(fallback)

        return jsonify(result)
    except ModrinthApiError as exc:
        return _modrinth_error_response(exc)


@modrinth_bp.route('/mod/<mod_id>', methods=['GET'])
def get_mod(mod_id):
    try:
        result = modrinth_client.get_mod(mod_id)
        return jsonify(result)
    except ModrinthApiError as exc:
        return _modrinth_error_response(exc)


@modrinth_bp.route('/project/<project_id>', methods=['GET'])
def get_project(project_id):
    try:
        result = modrinth_client.get_project(project_id)
        return jsonify(result)
    except ModrinthApiError as exc:
        return _modrinth_error_response(exc)


@modrinth_bp.route('/mod/<mod_id>/versions', methods=['GET'])
def get_mod_versions(mod_id):
    loaders = request.args.getlist('loaders')
    game_versions = request.args.getlist('game_versions')
    featured = request.args.get('featured')

    featured_bool = None
    if featured is not None:
        featured_bool = featured.lower() in ('true', '1', 'yes')

    try:
        result = modrinth_client.get_mod_versions(
            mod_id=mod_id,
            loaders=loaders if loaders else None,
            game_versions=game_versions if game_versions else None,
            featured=featured_bool
        )
        return jsonify(result)
    except ModrinthApiError as exc:
        return _modrinth_error_response(exc)


@modrinth_bp.route('/project/<project_id>/versions', methods=['GET'])
def get_project_versions(project_id):
    loaders = request.args.getlist('loaders')
    game_versions = request.args.getlist('game_versions')
    featured = request.args.get('featured')

    featured_bool = None
    if featured is not None:
        featured_bool = featured.lower() in ('true', '1', 'yes')

    try:
        result = modrinth_client.get_project_versions(
            project_id=project_id,
            loaders=loaders if loaders else None,
            game_versions=game_versions if game_versions else None,
            featured=featured_bool
        )
        return jsonify(result)
    except ModrinthApiError as exc:
        return _modrinth_error_response(exc)


@modrinth_bp.route('/project/<project_id>/resolve-version', methods=['GET'])
def resolve_project_version(project_id):
    mc_version = request.args.get('mc_version')
    loader = request.args.get('loader')

    if not mc_version:
        return jsonify({"error": "mc_version parameter is required"}), 400

    try:
        resolved = modrinth_client.resolve_project_version(
            project_id=project_id,
            mc_version=mc_version,
            loader=loader
        )
    except ModrinthApiError as exc:
        return _modrinth_error_response(exc)

    if not resolved:
        return jsonify({"error": "No suitable version found"}), 404

    return jsonify({
        "project_id": project_id,
        "mc_version": mc_version,
        "loader": loader,
        "version": resolved["version"],
        "download_url": resolved["download_url"]
    })


@modrinth_bp.route('/mod/<mod_id>/download-url', methods=['GET'])
def get_mod_download_url(mod_id):
    mc_version = request.args.get('mc_version')
    loader = request.args.get('loader', 'fabric')

    if not mc_version:
        return jsonify({"error": "mc_version parameter is required"}), 400

    try:
        download_url = modrinth_client.get_mod_download_url(
            mod_id=mod_id,
            mc_version=mc_version,
            loader=loader
        )
    except ModrinthApiError as exc:
        return _modrinth_error_response(exc)

    if not download_url:
        return jsonify({"error": "No suitable version found"}), 404

    return jsonify({"download_url": download_url})


@modrinth_bp.route('/mod/<mod_id>/install', methods=['POST'])
def install_mod(mod_id):
    data = request.get_json() or {}
    mc_version = data.get('mc_version')
    loader = data.get('loader', 'fabric')
    server_id = data.get('server_id')
    mods_folder_override = data.get('mods_folder')

    if not mc_version:
        return jsonify({"error": "mc_version is required"}), 400

    if not server_id:
        return jsonify({"error": "server_id is required"}), 400

    if mods_folder_override:
        return jsonify({"error": "mods_folder override is not allowed"}), 400

    mods_folder, error = _resolve_mods_folder(server_id)
    if error:
        payload, status = error
        return jsonify(payload), status

    target_path = Path(mods_folder)

    try:
        download_url = modrinth_client.get_mod_download_url(
            mod_id=mod_id,
            mc_version=mc_version,
            loader=loader
        )
    except ModrinthApiError as exc:
        return _modrinth_error_response(exc)

    if not download_url:
        return jsonify({"error": "No suitable version found"}), 404

    try:
        file_path = modrinth_client.download_mod(download_url, target_path)
    except ModrinthApiError as exc:
        return _modrinth_error_response(exc)

    return jsonify({
        "success": True,
        "message": "Mod installed successfully",
        "file": str(file_path.name),
        "path": str(file_path)
    })


@modrinth_bp.route('/modpack/<project_id>/install', methods=['POST'])
def install_modpack(project_id):
    data = request.get_json() or {}
    mc_version = data.get('mc_version')
    loader = data.get('loader')
    server_id = data.get('server_id')
    clean_install = True
    create_backup = _parse_bool(data.get('create_backup'), default=False)
    allow_missing = _parse_bool(data.get('allow_missing'), default=False)
    mod_side_overrides = data.get('mod_side_overrides')

    if not server_id:
        return jsonify({'error': 'server_id is required'}), 400

    server = storage.get_server(server_id)
    if not server:
        return jsonify({'error': 'Server not found'}), 404

    runtime_status = process_registry.get_status(server_id)
    if runtime_status.get('status') == 'running':
        return jsonify({'error': 'Stop the server before installing a modpack'}), 400

    try:
        install_path = process_registry._resolve_install_path(server)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    backup_file = None
    if create_backup:
        try:
            backup_file = _create_server_backup(install_path)
        except OSError as exc:
            return jsonify({'error': f'Failed to create backup before install: {exc}'}), 500

    try:
        install_kwargs = {
            'project_id': project_id,
            'install_path': install_path,
            'mc_version': mc_version,
            'loader': loader,
        }

        # Backward compatibility: tolerate older cached client code that does
        # not yet expose the clean_install argument.
        if 'clean_install' in inspect.signature(modrinth_client.install_modpack).parameters:
            install_kwargs['clean_install'] = clean_install
        if 'allow_missing' in inspect.signature(modrinth_client.install_modpack).parameters:
            install_kwargs['allow_missing'] = allow_missing
        if 'mod_side_overrides' in inspect.signature(modrinth_client.install_modpack).parameters:
            install_kwargs['mod_side_overrides'] = mod_side_overrides

        result = modrinth_client.install_modpack(**install_kwargs)
    except ModrinthApiError as exc:
        return _modrinth_error_response(exc)
    except Exception as exc:  # pragma: no cover - defensive error mapping
        current_app.logger.exception('Unexpected modpack install failure for %s', project_id)
        return jsonify({'error': f'Modpack install failed: {exc}'}), 500

    payload = {'success': True, 'message': 'Modpack installed successfully', **result}
    if backup_file:
        payload['backup_file'] = backup_file
    return jsonify(payload)


@modrinth_bp.route('/version/<version_id>', methods=['GET'])
def get_version(version_id):
    try:
        result = modrinth_client.get_version(version_id)
        return jsonify(result)
    except ModrinthApiError as exc:
        return _modrinth_error_response(exc)


@modrinth_bp.route('/categories', methods=['GET'])
def get_categories():
    try:
        result = modrinth_client.get_categories()
        return jsonify(result)
    except ModrinthApiError as exc:
        return _modrinth_error_response(exc)


@modrinth_bp.route('/loaders', methods=['GET'])
def get_loaders():
    try:
        result = modrinth_client.get_loaders()
        return jsonify(result)
    except ModrinthApiError as exc:
        return _modrinth_error_response(exc)


@modrinth_bp.route('/game-versions', methods=['GET'])
def get_game_versions():
    try:
        result = modrinth_client.get_game_versions()
        return jsonify(result)
    except ModrinthApiError as exc:
        return _modrinth_error_response(exc)
