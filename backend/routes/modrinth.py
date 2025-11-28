"""Modrinth API routes."""
import os
from pathlib import Path
from flask import Blueprint, jsonify, request

from backend.services import server_storage
from backend.services.modrinth_client import ModrinthClient
from backend.services.server_registry import get_server_process_registry

modrinth_bp = Blueprint('modrinth', __name__, url_prefix='/api/modrinth')
modrinth_client = ModrinthClient()
process_registry = get_server_process_registry()


def _resolve_mods_folder(server_id: str | None):
    if server_id:
        server = server_storage.get_server(server_id)
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
    """
    Search for mods on Modrinth.
    
    Query params:
        - query: Search text
        - mc_version: Minecraft version (e.g., "1.20.1")
        - loader: Mod loader (e.g., "fabric", "forge")
        - limit: Results per page (default 20, max 100)
        - offset: Pagination offset
        - index: Sort by (downloads, relevance, follows, newest, updated)
    """
    query = request.args.get('query', '')
    mc_version = request.args.get('mc_version')
    loader = request.args.get('loader')
    limit = int(request.args.get('limit', 20))
    offset = int(request.args.get('offset', 0))
    index = request.args.get('index', 'downloads')
    
    result = modrinth_client.search_mods(
        query=query,
        mc_version=mc_version,
        loader=loader,
        limit=limit,
        offset=offset,
        index=index
    )
    return jsonify(result)


@modrinth_bp.route('/mod/<mod_id>', methods=['GET'])
def get_mod(mod_id):
    """Get detailed information about a specific mod."""
    result = modrinth_client.get_mod(mod_id)
    return jsonify(result)


@modrinth_bp.route('/mod/<mod_id>/versions', methods=['GET'])
def get_mod_versions(mod_id):
    """
    Get all versions of a mod.
    
    Query params:
        - loaders: Comma-separated loaders (e.g., "fabric,forge")
        - game_versions: Comma-separated game versions (e.g., "1.20.1,1.20.2")
        - featured: Filter for featured versions (true/false)
    """
    loaders = request.args.getlist('loaders')
    game_versions = request.args.getlist('game_versions')
    featured = request.args.get('featured')
    
    # Convert featured string to boolean if provided
    featured_bool = None
    if featured is not None:
        featured_bool = featured.lower() in ('true', '1', 'yes')
    
    result = modrinth_client.get_mod_versions(
        mod_id=mod_id,
        loaders=loaders if loaders else None,
        game_versions=game_versions if game_versions else None,
        featured=featured_bool
    )
    return jsonify(result)


@modrinth_bp.route('/mod/<mod_id>/download-url', methods=['GET'])
def get_mod_download_url(mod_id):
    """
    Get the direct download URL for a mod's best matching version.
    
    Query params:
        - mc_version: Minecraft version (required, e.g., "1.20.1")
        - loader: Mod loader (default: "fabric")
    """
    mc_version = request.args.get('mc_version')
    loader = request.args.get('loader', 'fabric')
    
    if not mc_version:
        return jsonify({"error": "mc_version parameter is required"}), 400
    
    download_url = modrinth_client.get_mod_download_url(
        mod_id=mod_id,
        mc_version=mc_version,
        loader=loader
    )
    
    if not download_url:
        return jsonify({"error": "No suitable version found"}), 404
    
    return jsonify({"download_url": download_url})


@modrinth_bp.route('/mod/<mod_id>/install', methods=['POST'])
def install_mod(mod_id):
    """
    Download and install a mod to the server's mods folder.
    
    Body params (JSON):
        - mc_version: Minecraft version (required, e.g., "1.20.1")
        - loader: Mod loader (default: "fabric")
        - server_id: Target server ID (optional, defaults to legacy single server)
    """
    data = request.get_json() or {}
    mc_version = data.get('mc_version')
    loader = data.get('loader', 'fabric')
    server_id = data.get('server_id')
    mods_folder_override = data.get('mods_folder')
    
    if not mc_version:
        return jsonify({"error": "mc_version is required"}), 400

    if mods_folder_override:
        return jsonify({"error": "mods_folder override is not allowed"}), 400
    
    mods_folder, error = _resolve_mods_folder(server_id)
    if error:
        payload, status = error
        return jsonify(payload), status
    
    target_path = Path(mods_folder)
    
    # Get download URL
    download_url = modrinth_client.get_mod_download_url(
        mod_id=mod_id,
        mc_version=mc_version,
        loader=loader
    )
    
    if not download_url:
        return jsonify({"error": "No suitable version found"}), 404
    
    # Download the mod
    file_path = modrinth_client.download_mod(download_url, target_path)
    
    if not file_path:
        return jsonify({"error": "Download failed"}), 500
    
    return jsonify({
        "success": True,
        "message": f"Mod installed successfully",
        "file": str(file_path.name),
        "path": str(file_path)
    })


@modrinth_bp.route('/version/<version_id>', methods=['GET'])
def get_version(version_id):
    """Get detailed information about a specific mod version."""
    result = modrinth_client.get_version(version_id)
    return jsonify(result)


@modrinth_bp.route('/categories', methods=['GET'])
def get_categories():
    """Get all available mod categories."""
    result = modrinth_client.get_categories()
    return jsonify(result)


@modrinth_bp.route('/loaders', methods=['GET'])
def get_loaders():
    """Get all available mod loaders."""
    result = modrinth_client.get_loaders()
    return jsonify(result)


@modrinth_bp.route('/game-versions', methods=['GET'])
def get_game_versions():
    """Get all available game versions."""
    result = modrinth_client.get_game_versions()
    return jsonify(result)
