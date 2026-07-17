"""Modrinth API routes."""
import threading
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from flask import Blueprint, current_app, jsonify, request

from backend.modrinth.client import ModrinthClient, ModrinthApiError
from backend.server import storage
from backend.server.registry import get_server_process_registry
from backend.server.java_compat import resolve_required_java, skip_java_enforcement
from backend.utils.routes import require_server, with_server_lock
from backend.utils.strings import bool_from_str
from backend.utils.time import iso_z_now

modrinth_bp = Blueprint('modrinth', __name__, url_prefix='/api/modrinth')
modrinth_client = ModrinthClient()


def _registry():
    """Lazy accessor for the process registry."""
    return get_server_process_registry()

_install_progress_lock = threading.Lock()
_install_progress: dict[str, dict] = {}


def _update_install_progress(server_id: str, **kwargs):
    with _install_progress_lock:
        _install_progress[server_id] = {
            **(_install_progress.get(server_id) or {}),
            **kwargs,
            'updated_at': iso_z_now(),
        }


def _get_install_progress(server_id: str) -> dict:
    with _install_progress_lock:
        return dict(_install_progress.get(server_id) or {})


def _clear_install_progress(server_id: str):
    with _install_progress_lock:
        _install_progress.pop(server_id, None)


def _modrinth_error_response(exc: ModrinthApiError):
    status = exc.status_code or 502
    payload = {'error': str(exc)}
    details = getattr(exc, 'details', None)
    if isinstance(details, dict):
        payload.update(details)
    return jsonify(payload), status


def _parse_bool(value, default: bool = False) -> bool:
    """Parse a flexible bool from JSON values (None/bool/int/float/str).

    Note: as of B6, whitespace-stripping is delegated to ``bool_from_str`` —
    leading/trailing whitespace in the input is now treated as a no-op
    (``'  true  '`` parses to ``True``). Benign behavior change vs. the
    pre-B6 strict-match implementation.
    """
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return bool_from_str(value)
    return default


def _create_server_backup(install_path: Path) -> str:
    backups_dir = install_path / 'backups'
    backups_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')
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


def _server_loader_facets(server: dict, fallback_loader: str) -> list:
    """Modrinth loader facets accepted for ``server``.

    For plugin servers this is the platform's compatibility chain (e.g. Paper
    accepts paper/spigot/bukkit plugins); for mod loaders it's just the single
    loader. Falls back to the request-supplied loader if the installer can't be
    resolved. Used so plugin resolution matches versions tagged with any
    accepted facet, not only the exact loader name.
    """
    from backend.server.installer import get_installer_for

    loader = str(server.get('loader') or '').strip().lower()
    installer = get_installer_for(loader, Path('.'))
    if installer and installer.modrinth_loader_facets:
        return installer.modrinth_loader_facets
    return [fallback_loader] if fallback_loader else []


def _record_content_install(server_id: str, mod_id: str, filename: str, resolved: dict) -> None:
    """Record ``filename`` -> Modrinth project in the server's manifest.

    Best-effort: the jar is already on disk and usable, so a failure to fetch
    project metadata (or to write the manifest) must not fail the install. The
    UI degrades to the filename-prefix guess in that case, exactly as it did
    before the manifest existed.
    """
    entry = {
        'projectId': mod_id,
        'versionId': resolved.get('version_id'),
        'versionNumber': resolved.get('version_number'),
        'installedAt': iso_z_now(),
    }
    try:
        project = modrinth_client.get_project(mod_id)
        entry.update({
            'projectId': project.get('id') or mod_id,
            'slug': project.get('slug'),
            'title': project.get('title'),
            'iconUrl': project.get('icon_url'),
        })
    except ModrinthApiError:
        current_app.logger.warning(
            'Could not fetch Modrinth project %s for manifest; recording id only', mod_id
        )
    try:
        storage.record_content_install(server_id, filename, entry)
    except OSError as exc:
        current_app.logger.warning('Failed to record install manifest for %s: %s', filename, exc)


def _resolve_mods_folder(server: dict):
    """Resolve ``server``'s mods folder via the registry.

    Takes the already-validated server dict (typically from
    ``@require_server``) so we don't make a redundant ``storage.get_server``
    call. Returns ``(path, None)`` on success or ``(None, (payload, status))``
    on a registry-level ``ValueError`` (e.g. install path config issue).
    """
    try:
        path = _registry().resolve_mods_path(server)
        return path, None
    except ValueError as exc:
        return None, ({'error': str(exc)}, 400)


@modrinth_bp.route('/search', methods=['GET'])
def search_mods():
    query = request.args.get('query', '')
    mc_version = request.args.get('mc_version')
    loader = request.args.get('loader')
    # Bukkit-family servers browse Modrinth *plugins* through this same route;
    # only 'mod' and 'plugin' are accepted so a bad value can't reshape the facet.
    project_type = request.args.get('project_type', 'mod')
    if project_type not in ('mod', 'plugin'):
        project_type = 'mod'
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
        result = modrinth_client.search(
            project_type=project_type,
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
        result = modrinth_client.search(
            project_type='modpack',
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


@modrinth_bp.route('/mod/<mod_id>', methods=['GET'])
def get_mod(mod_id):
    try:
        result = modrinth_client.get_project(mod_id)
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
        featured_bool = bool_from_str(featured)

    try:
        result = modrinth_client.get_project_versions(
            project_id=mod_id,
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
        featured_bool = bool_from_str(featured)

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
    # Optional comma-joined facet chain (plugin servers accept paper/spigot/
    # bukkit); when present it supersedes the single ``loader`` so a plugin
    # tagged only 'spigot' still resolves for a Paper server.
    loaders_raw = request.args.get('loaders')
    loaders = (
        [part.strip() for part in loaders_raw.split(',') if part.strip()]
        if loaders_raw else None
    )

    if not mc_version:
        return jsonify({"error": "mc_version parameter is required"}), 400

    try:
        resolved = modrinth_client.resolve_project_version(
            project_id=project_id,
            mc_version=mc_version,
            loader=loader,
            loaders=loaders
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


# Public HTTP route stays `/mod/<mod_id>/download-url` for backward compat
# (B14b precedent: legacy `/mod/` route co-exists with new `/project/` route).
# The view function name and the URL placeholder name retain `mod_id` to
# match the URL surface; only the client-method internal name was renamed
# to ``get_project_download_url`` in B15.5d.
@modrinth_bp.route('/mod/<mod_id>/download-url', methods=['GET'])
def get_mod_download_url(mod_id):
    mc_version = request.args.get('mc_version')
    loader = request.args.get('loader', 'fabric')

    if not mc_version:
        return jsonify({"error": "mc_version parameter is required"}), 400

    try:
        resolved = modrinth_client.get_project_download_url(
            project_id=mod_id, mc_version=mc_version, loader=loader
        )
    except ModrinthApiError as exc:
        return _modrinth_error_response(exc)

    if not resolved:
        return jsonify({"error": "No suitable version found"}), 404

    return jsonify({"download_url": resolved["url"]})


@modrinth_bp.route('/mod/<mod_id>/install', methods=['POST'])
@require_server(source='body')
@with_server_lock(source='body')
def install_mod(mod_id, server):
    # 4xx fan-out order (post-B14a, pinned by tests/test_modrinth_routes_4xx_order.py):
    # 1. 400 missing server_id           (@require_server source='body')
    # 2. 404 server not found            (@require_server)
    # 3. 409 lock busy                   (@with_server_lock)
    # 4. 400 missing mc_version          (handler body)
    # 5. 400 mods_folder override        (handler body)
    # 6. 400 mods-folder resolve error   (handler body, _resolve_mods_folder ValueError)
    # 7. 404 no resolved version         (handler body)
    data = request.get_json() or {}
    mc_version = data.get('mc_version')
    loader = data.get('loader', 'fabric')
    server_id = data.get('server_id')
    mods_folder_override = data.get('mods_folder')

    if not mc_version:
        return jsonify({"error": "mc_version is required"}), 400

    if mods_folder_override:
        return jsonify({"error": "mods_folder override is not allowed"}), 400

    mods_folder, error = _resolve_mods_folder(server)
    if error:
        payload, status = error
        return jsonify(payload), status

    target_path = Path(mods_folder)

    # Plugin servers accept a facet chain (paper/spigot/bukkit); mod loaders
    # resolve as the single loader. Derive from the server so a plugin tagged
    # only 'spigot' still resolves for a Paper server.
    loader_facets = _server_loader_facets(server, loader)

    try:
        resolved = modrinth_client.get_project_download_url(
            project_id=mod_id, mc_version=mc_version, loader=loader,
            loaders=loader_facets,
        )
    except ModrinthApiError as exc:
        return _modrinth_error_response(exc)

    if not resolved:
        return jsonify({"error": "No suitable version found"}), 404

    try:
        file_path = modrinth_client.download_mod(
            resolved["url"], target_path, hashes=resolved["hashes"]
        )
    except ModrinthApiError as exc:
        return _modrinth_error_response(exc)

    _record_content_install(server_id, mod_id, file_path.name, resolved)

    return jsonify({
        "success": True,
        "message": "Mod installed successfully",
        "file": str(file_path.name),
        "path": str(file_path)
    })


@modrinth_bp.route('/modpack/<project_id>/install', methods=['POST'])
@require_server(source='body')
@with_server_lock(
    source='body',
    busy_message='A modpack install is already in progress for this server',
)
def install_modpack(project_id, server):
    data = request.get_json() or {}
    mc_version = data.get('mc_version')
    loader = data.get('loader')
    server_id = data.get('server_id')
    clean_install = _parse_bool(data.get('clean_install'), default=True)
    create_backup = _parse_bool(data.get('create_backup'), default=True)
    allow_missing = _parse_bool(data.get('allow_missing'), default=False)
    mod_side_overrides = data.get('mod_side_overrides')

    runtime_status = _registry().get_status(server_id)
    if runtime_status.get('status') == 'running':
        return jsonify({'error': 'Stop the server before installing a modpack'}), 400

    try:
        install_path = _registry().resolve_install_path(server)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    backup_file = None
    if create_backup:
        try:
            backup_file = _create_server_backup(install_path)
        except OSError as exc:
            return jsonify({'error': f'Failed to create backup before install: {exc}'}), 500

    def _progress_cb(stage='', current=0, total=0, detail=''):
        _update_install_progress(server_id, stage=stage, current=current, total=total, detail=detail)

    _update_install_progress(server_id, stage='starting', current=0, total=0, detail='')

    try:
        result = modrinth_client.install_modpack(
            project_id=project_id,
            install_path=install_path,
            mc_version=mc_version,
            loader=loader,
            clean_install=clean_install,
            allow_missing=allow_missing,
            mod_side_overrides=mod_side_overrides,
            progress_callback=_progress_cb,
        )
    except ModrinthApiError as exc:
        _clear_install_progress(server_id)
        return _modrinth_error_response(exc)
    except Exception as exc:  # pragma: no cover - defensive error mapping
        _clear_install_progress(server_id)
        current_app.logger.exception('Unexpected modpack install failure for %s', project_id)
        return jsonify({'error': f'Modpack install failed: {exc}'}), 500

    _update_install_progress(server_id, stage='done', current=0, total=0, detail='')

    if clean_install:
        # A clean install replaces mods/ wholesale, so every recorded jar is
        # gone; stale entries would mislabel whatever the pack dropped in.
        storage.clear_content_manifest(server_id)

    modpack_info = {
        'projectId': project_id,
        'versionId': result.get('version_id'),
        'name': result.get('name'),
        'version': result.get('version'),
        'mcVersion': result.get('mc_version'),
        'loaders': result.get('loaders', []),
        'installedAt': iso_z_now(),
    }
    storage.update_server(server_id, {'modpack': modpack_info})
    _clear_install_progress(server_id)

    # NOTE: with @with_server_lock the per-server lock now covers this
    # post-install java-warning compute (previously released earlier).
    # The added scope is read-only on storage and registry so the only
    # observable effect is that a contending request waits a few extra
    # ms — acceptable and arguably safer.
    java_warning = None
    effective_mc = result.get('mc_version') or mc_version or server.get('version', '')
    if effective_mc and not skip_java_enforcement():
        compat = resolve_required_java(effective_mc)
        if compat.enforceable:
            runtime = _registry().get_java_runtime(server)
            detected = runtime.get('major_version')
            if detected is None or detected < compat.required_java:
                java_warning = {
                    'required_java': compat.required_java,
                    'detected_java': detected,
                    'message': (
                        f'This server needs Java {compat.required_java}+ for Minecraft {effective_mc}'
                        f' (detected: {detected if detected is not None else "none"}).'
                    ),
                }

    payload = {'success': True, 'message': 'Modpack installed successfully', **result}
    if backup_file:
        payload['backup_file'] = backup_file
    if java_warning:
        payload['java_warning'] = java_warning
    return jsonify(payload)


@modrinth_bp.route('/modpack/install-progress/<server_id>', methods=['GET'])
def get_modpack_install_progress(server_id):
    progress = _get_install_progress(server_id)
    if not progress:
        return jsonify({'active': False})
    return jsonify({'active': True, **progress})


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
