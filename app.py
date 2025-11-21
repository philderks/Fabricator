from flask import Flask, jsonify, request
from flask_cors import CORS
import os

from server_service import ServerService
from backend.ModrinthApi import ModrinthAPI

app = Flask(__name__)
CORS(app)

server_service = ServerService()
modrinth_api = ModrinthAPI()


@app.route('/api/status', methods=['GET'])
def get_status():
    """Return the current status of the managed server."""
    status = server_service.status()
    status.update({"version": "1.0.0"})
    return jsonify(status)


@app.route('/api/start', methods=['POST'])
def start_server():
    """Start the managed server process."""
    result = server_service.start()
    return jsonify(result)


@app.route('/api/stop', methods=['POST'])
def stop_server():
    """Stop the managed server process."""
    result = server_service.stop()
    return jsonify(result)


@app.route('/api/health', methods=['GET'])
def health_check():
    """Simple health check endpoint."""
    return jsonify({'healthy': True})


# Modrinth API endpoints
@app.route('/api/modrinth/search', methods=['GET'])
def search_mods():
    """Search for mods on Modrinth."""
    query = request.args.get('query', '')
    limit = int(request.args.get('limit', 20))
    offset = int(request.args.get('offset', 0))
    index = request.args.get('index', 'relevance')
    
    # Parse facets if provided
    facets = None
    facets_param = request.args.get('facets')
    if facets_param:
        import json
        try:
            facets = json.loads(facets_param)
        except json.JSONDecodeError:
            pass
    
    result = modrinth_api.search_mods(
        query=query,
        facets=facets,
        limit=limit,
        offset=offset,
        index=index
    )
    return jsonify(result)


@app.route('/api/modrinth/mod/<mod_id>', methods=['GET'])
def get_mod(mod_id):
    """Get detailed information about a specific mod."""
    result = modrinth_api.get_mod(mod_id)
    return jsonify(result)


@app.route('/api/modrinth/mod/<mod_id>/versions', methods=['GET'])
def get_mod_versions(mod_id):
    """Get all versions of a mod."""
    loaders = request.args.getlist('loaders')
    game_versions = request.args.getlist('game_versions')
    
    result = modrinth_api.get_mod_versions(
        mod_id=mod_id,
        loaders=loaders if loaders else None,
        game_versions=game_versions if game_versions else None
    )
    return jsonify(result)


@app.route('/api/modrinth/version/<version_id>', methods=['GET'])
def get_version(version_id):
    """Get detailed information about a specific mod version."""
    result = modrinth_api.get_version(version_id)
    return jsonify(result)


@app.route('/api/modrinth/categories', methods=['GET'])
def get_categories():
    """Get all available mod categories."""
    result = modrinth_api.get_categories()
    return jsonify(result)


@app.route('/api/modrinth/loaders', methods=['GET'])
def get_loaders():
    """Get all available mod loaders."""
    result = modrinth_api.get_loaders()
    return jsonify(result)


@app.route('/api/modrinth/game-versions', methods=['GET'])
def get_game_versions():
    """Get all available game versions."""
    result = modrinth_api.get_game_versions()
    return jsonify(result)


if __name__ == '__main__':
    debug_mode = os.environ.get('FLASK_ENV') != 'production'
    app.run(debug=debug_mode, host='0.0.0.0', port=5000)
