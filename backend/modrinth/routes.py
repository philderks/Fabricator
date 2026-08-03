"""Modrinth API routes."""
import threading
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from flask import Blueprint, current_app, jsonify, request
from werkzeug.utils import secure_filename

from backend.modrinth import installed, mrpack
from backend.modrinth.client import ModrinthClient, ModrinthApiError
from backend.server import storage
from backend.server.registry import get_server_process_registry
from backend.server.java_compat import resolve_required_java, skip_java_enforcement
from backend.utils.routes import require_server, with_server_lock
from backend.utils.strings import bool_from_str
from backend.utils.time import iso_z_now
from backend.utils.upload import UploadTooLargeError, stream_upload_to_temp

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
    """Map a client error onto a response, carrying `retry_after` through.

    The client populates ``details['retry_after']`` for 429s (from Modrinth's
    Retry-After, or from our own limiter cooldown). The frontend's backoff
    helper reads exactly that field off the body, so forwarding it is what
    lets a retry wait the right amount of time instead of guessing (#52).
    """
    status = exc.status_code or 502
    payload = {'error': str(exc)}
    details = getattr(exc, 'details', None)
    if isinstance(details, dict):
        payload.update(details)
    response = jsonify(payload)
    if status == 429 and isinstance(details, dict) and details.get('retry_after') is not None:
        # Also as a real header, for anything that speaks HTTP rather than our
        # JSON envelope (curl, a reverse proxy, the browser devtools panel).
        response.headers['Retry-After'] = str(int(float(details['retry_after']) + 0.5))
    return response, status


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


def _record_content_install(
    server_id: str, mod_id: str, filename: str, resolved: dict, pinned: bool = False
) -> None:
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
        # True when the user named this version rather than taking whatever
        # resolved as newest. Lets the UI mark it, and lets a future
        # update-all leave deliberate pins alone (#56).
        'pinned': bool(pinned),
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


def _resolve_replaceable_jar(mods_folder: Path, filename: str):
    """Resolve the jar a version swap supersedes, or an error tuple.

    ``replaces`` comes from the client and names a file we are about to delete,
    so it is treated as untrusted: only a bare filename is accepted, and the
    resolved path must still land inside the mods folder. That blocks
    ``../../server.jar`` and a symlink pointing out of the tree alike.

    A missing file is not an error — the user may have removed the old jar by
    hand between opening the picker and confirming, and the install should
    still proceed.
    """
    raw = str(filename).strip()
    if not raw or raw != Path(raw).name:
        return None, ({'error': 'replaces must be a bare filename'}, 400)
    if not raw.lower().endswith('.jar'):
        return None, ({'error': 'replaces must name a .jar file'}, 400)

    candidate = (mods_folder / raw).resolve()
    try:
        candidate.relative_to(mods_folder.resolve())
    except ValueError:
        return None, ({'error': 'replaces must name a file in the mods folder'}, 400)

    if not candidate.is_file():
        return None, None
    return candidate, None


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


@modrinth_bp.route('/servers/<server_id>/resolve-installed', methods=['GET'])
@require_server
def resolve_installed_mods(server_id, server):
    """Identify every jar in the server's mods folder by content hash.

    Replaces the frontend's filename-prefix guessing, which issued ~3.6
    requests per jar and blew Modrinth's 300/min budget on any hand-populated
    modpack folder (#52). Costs ~2 upstream requests for a whole folder, and
    none once cached.

    Returns ``{resolved: {filename: meta}}``. Jars Modrinth doesn't recognise
    (hand-modified, repackaged, or never published there) are simply absent —
    the caller falls back to the filename for those.
    """
    mods_folder, error = _resolve_mods_folder(server)
    if error:
        payload, status = error
        return jsonify(payload), status

    mods_path = Path(mods_folder)
    if not mods_path.is_dir():
        return jsonify({'resolved': {}})

    jars = sorted(
        path for path in mods_path.iterdir()
        if path.is_file() and path.suffix.lower() == '.jar'
    )

    try:
        resolved = installed.resolve_jar_files(modrinth_client, jars)
    except ModrinthApiError as exc:
        return _modrinth_error_response(exc)

    return jsonify({'resolved': resolved})


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
    # #56: name a version instead of taking whatever resolves as newest. Also
    # the mechanism behind "change version" on an installed mod, which is an
    # install of a chosen version plus removal of the jar it supersedes.
    version_id = data.get('version_id')
    replaces = data.get('replaces')

    if not mc_version:
        return jsonify({"error": "mc_version is required"}), 400

    if mods_folder_override:
        return jsonify({"error": "mods_folder override is not allowed"}), 400

    mods_folder, error = _resolve_mods_folder(server)
    if error:
        payload, status = error
        return jsonify(payload), status

    target_path = Path(mods_folder)

    replaced_path = None
    if replaces:
        replaced_path, error = _resolve_replaceable_jar(target_path, replaces)
        if error:
            payload, status = error
            return jsonify(payload), status

    # Plugin servers accept a facet chain (paper/spigot/bukkit); mod loaders
    # resolve as the single loader. Derive from the server so a plugin tagged
    # only 'spigot' still resolves for a Paper server.
    loader_facets = _server_loader_facets(server, loader)

    try:
        if version_id:
            # No compatibility filtering: naming a version is an explicit
            # override, and refusing it here would defeat the point — pinning
            # an older build for compatibility is exactly the use case (#56).
            # The frontend surfaces which versions target this server.
            resolved = modrinth_client.get_pinned_download(mod_id, version_id)
        else:
            resolved = modrinth_client.get_project_download_url(
                project_id=mod_id, mc_version=mc_version, loader=loader,
                loaders=loader_facets,
            )
    except ModrinthApiError as exc:
        return _modrinth_error_response(exc)

    if not resolved:
        return jsonify({
            "error": "That version has no downloadable file" if version_id
            else "No suitable version found"
        }), 404

    try:
        file_path = modrinth_client.download_mod(
            resolved["url"], target_path, hashes=resolved["hashes"]
        )
    except ModrinthApiError as exc:
        return _modrinth_error_response(exc)

    _record_content_install(
        server_id, mod_id, file_path.name, resolved, pinned=bool(version_id)
    )

    # Only after the replacement is on disk: a failed download must leave the
    # old jar in place rather than the server with no copy of the mod at all.
    replaced = None
    if replaced_path is not None and replaced_path.name != file_path.name:
        try:
            replaced_path.unlink()
            storage.forget_content(server_id, [replaced_path.name])
            replaced = replaced_path.name
        except OSError as exc:
            current_app.logger.warning(
                'Installed %s but could not remove the superseded %s: %s',
                file_path.name, replaced_path.name, exc
            )

    return jsonify({
        "success": True,
        "message": "Mod installed successfully",
        "file": str(file_path.name),
        "path": str(file_path),
        "versionId": resolved.get("version_id"),
        "versionNumber": resolved.get("version_number"),
        "replaced": replaced,
    })


def _run_modpack_install(server, data, run_install, build_modpack_info, *, log_label):
    """Run a modpack install and everything that has to happen around one.

    The pack's origin — a Modrinth project or an uploaded .mrpack (#53) —
    changes only ``run_install`` (how the files get there) and
    ``build_modpack_info`` (what identity is recorded on the server). The
    stopped-server guard, the pre-install backup, progress bookkeeping, the
    content-manifest reset and the Java warning are the same either way.

    ``run_install(install_path, progress_cb)`` returns the client's result
    dict. Returns a Flask response — a bare one on success, a
    ``(body, status)`` tuple on every failure path.
    """
    server_id = data.get('server_id')
    clean_install = _parse_bool(data.get('clean_install'), default=True)
    create_backup = _parse_bool(data.get('create_backup'), default=True)

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
        result = run_install(install_path, _progress_cb)
    except ModrinthApiError as exc:
        _clear_install_progress(server_id)
        return _modrinth_error_response(exc)
    except Exception as exc:  # pragma: no cover - defensive error mapping
        _clear_install_progress(server_id)
        current_app.logger.exception('Unexpected modpack install failure for %s', log_label)
        return jsonify({'error': f'Modpack install failed: {exc}'}), 500

    _update_install_progress(server_id, stage='done', current=0, total=0, detail='')

    if clean_install:
        # A clean install replaces mods/ wholesale, so every recorded jar is
        # gone; stale entries would mislabel whatever the pack dropped in.
        storage.clear_content_manifest(server_id)

    storage.update_server(server_id, {'modpack': build_modpack_info(result)})
    _clear_install_progress(server_id)

    # NOTE: with @with_server_lock the per-server lock now covers this
    # post-install java-warning compute (previously released earlier).
    # The added scope is read-only on storage and registry so the only
    # observable effect is that a contending request waits a few extra
    # ms — acceptable and arguably safer.
    java_warning = None
    effective_mc = result.get('mc_version') or data.get('mc_version') or server.get('version', '')
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


@modrinth_bp.route('/modpack/<project_id>/install', methods=['POST'])
@require_server(source='body')
@with_server_lock(
    source='body',
    busy_message='A modpack install is already in progress for this server',
)
def install_modpack(project_id, server):
    data = request.get_json() or {}

    def _run(install_path, progress_cb):
        return modrinth_client.install_modpack(
            project_id=project_id,
            install_path=install_path,
            mc_version=data.get('mc_version'),
            loader=data.get('loader'),
            clean_install=_parse_bool(data.get('clean_install'), default=True),
            allow_missing=_parse_bool(data.get('allow_missing'), default=False),
            mod_side_overrides=data.get('mod_side_overrides'),
            progress_callback=progress_cb,
        )

    def _modpack_info(result):
        return {
            'projectId': project_id,
            'versionId': result.get('version_id'),
            'name': result.get('name'),
            'version': result.get('version'),
            'mcVersion': result.get('mc_version'),
            'loaders': result.get('loaders', []),
            'installedAt': iso_z_now(),
        }

    return _run_modpack_install(
        server, data, _run, _modpack_info, log_label=project_id
    )


@modrinth_bp.route('/modpack/upload', methods=['POST'])
def upload_modpack_archive():
    """Stage an uploaded .mrpack and report what it declares.

    The raw archive bytes are the request body (``fetch(url, {body: file})``);
    the display filename comes from the ``filename`` query param or the
    ``X-Filename`` header — the same shape as the world-import upload.

    Nothing is installed here. The response carries the Minecraft version and
    loader the pack was built against so the create form can fill itself in
    before the server it will be installed on even exists (#53).
    """
    original_name = (
        request.args.get('filename')
        or request.headers.get('X-Filename')
        or 'modpack.mrpack'
    )
    safe_display = secure_filename(original_name) or 'modpack.mrpack'

    max_bytes = mrpack.max_upload_bytes()
    if request.content_length and request.content_length > max_bytes:
        return jsonify({'error': f'Upload exceeds the {max_bytes}-byte limit'}), 413

    # Abandoned uploads (a create dialog closed without installing) are swept
    # here rather than on a timer: an upload is the only moment this feature
    # is guaranteed to be running.
    mrpack.sweep_expired()

    temp_path = mrpack.staging_dir() / f'mrpack-{uuid.uuid4().hex}.mrpack'
    try:
        written = stream_upload_to_temp(request.stream, temp_path, max_bytes=max_bytes)
    except UploadTooLargeError as exc:
        return jsonify({'error': str(exc)}), 413
    except OSError as exc:
        temp_path.unlink(missing_ok=True)
        return jsonify({'error': f'Failed to save the upload: {exc}'}), 500

    if written == 0:
        temp_path.unlink(missing_ok=True)
        return jsonify({'error': 'Empty upload — no file received'}), 400

    try:
        index = mrpack.read_index(temp_path)
    except mrpack.InvalidMrpackError as exc:
        temp_path.unlink(missing_ok=True)
        return jsonify({'error': str(exc)}), 400

    summary = mrpack.describe(index, temp_path)
    staged = mrpack.stage(
        temp_path, filename=safe_display, size_bytes=written, summary=summary
    )
    return jsonify({'success': True, **staged.to_payload()}), 201


@modrinth_bp.route('/modpack/upload/<upload_id>', methods=['DELETE'])
def discard_modpack_upload(upload_id):
    """Drop a staged .mrpack the user decided not to install."""
    if not mrpack.discard(upload_id):
        return jsonify({'error': 'Upload not found'}), 404
    return jsonify({'success': True})


@modrinth_bp.route('/modpack/upload/<upload_id>/install', methods=['POST'])
@require_server(source='body')
@with_server_lock(
    source='body',
    busy_message='A modpack install is already in progress for this server',
)
def install_uploaded_modpack(upload_id, server):
    """Install a previously staged .mrpack onto a server (#53)."""
    data = request.get_json() or {}
    staged = mrpack.get(upload_id)
    if staged is None:
        return jsonify({
            'error': 'That modpack upload is no longer available — upload the .mrpack again',
        }), 404

    # A pack declares what it was built against. Installing it onto a server
    # running something else generally produces a server that will not boot,
    # so the caller has to say so explicitly rather than find out later.
    if not _parse_bool(data.get('force'), default=False):
        mismatch = mrpack.compare_with_server(staged.summary, server)
        if mismatch:
            return jsonify({
                'error': 'This modpack does not match the server: ' + '; '.join(mismatch['reasons']),
                'can_continue_with_mismatch': True,
                **mismatch,
            }), 409

    loader = data.get('loader') or staged.summary.get('loader') or server.get('loader')

    def _run(install_path, progress_cb):
        return modrinth_client.install_mrpack_archive(
            staged.path,
            install_path,
            loader=loader,
            clean_install=_parse_bool(data.get('clean_install'), default=True),
            allow_missing=_parse_bool(data.get('allow_missing'), default=False),
            mod_side_overrides=data.get('mod_side_overrides'),
            progress_callback=progress_cb,
        )

    def _modpack_info(result):
        return {
            'projectId': None,
            'versionId': None,
            'name': result.get('name') or staged.filename,
            'version': result.get('version'),
            'mcVersion': result.get('mc_version'),
            'loaders': result.get('loaders', []),
            'source': 'upload',
            'fileName': staged.filename,
            'installedAt': iso_z_now(),
        }

    response = _run_modpack_install(
        server, data, _run, _modpack_info, log_label=staged.filename
    )

    # The staged archive outlives a failed install on purpose: the missing-files
    # and uncertain-mod-side flows retry the same pack once the user answers,
    # and re-uploading it to do that would be a poor trade. Anything left
    # behind is swept on the next upload.
    status = response[1] if isinstance(response, tuple) else response.status_code
    if status == 200:
        mrpack.discard(upload_id)
    return response


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
