"""Server management routes."""
from flask import Blueprint, jsonify, request

from backend.services.server_manager import ServerManager
from backend.services.server_registry import get_server_process_registry
from backend.services import server_storage

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
            updated = server_storage.update_server_status(server['id'], runtime_status)
            if updated:
                augmented = dict(updated)
                augmented['runtime'] = runtime
    return augmented


# Legacy single-server endpoints (kept for compatibility)
@server_bp.route('/status', methods=['GET'])
def get_status():
    """Return the current status of the managed server."""
    status = server_manager.status()
    status.update({"version": "1.0.0"})
    return jsonify(status)


@server_bp.route('/start', methods=['POST'])
def start_server_legacy():
    """Start the managed server process."""
    result = server_manager.start()
    return jsonify(result)


@server_bp.route('/stop', methods=['POST'])
def stop_server_legacy():
    """Stop the managed server process."""
    result = server_manager.stop()
    return jsonify(result)


@server_bp.route('/health', methods=['GET'])
def health_check():
    """Simple health check endpoint."""
    return jsonify({'healthy': True})


# Multi-server CRUD endpoints
@server_bp.route('/servers', methods=['GET'])
def get_servers():
    """Get list of all servers.
    
    Returns:
        JSON array of server objects
    """
    servers = [_augment_with_runtime(server) for server in server_storage.get_all_servers()]
    return jsonify(servers)


@server_bp.route('/servers', methods=['POST'])
def create_server():
    """Create a new server.
    
    Expected JSON body:
        - name: Server name
        - version: Minecraft version
        - loader: Mod loader (fabric, forge, etc.)
        - port: Server port
        - installPath: Installation directory
        - maxPlayers: Max players
        - difficulty: Difficulty level
        - gamemode: Default gamemode
        - ... (other settings)
    
    Returns:
        Created server object with generated ID
    """
    data = request.get_json()
    
    if not data:
        return jsonify({'error': 'Request body is required'}), 400
    
    # Validate required fields
    required_fields = ['name', 'version', 'loader', 'port', 'installPath']
    missing_fields = [field for field in required_fields if field not in data]
    
    if missing_fields:
        return jsonify({
            'error': f'Missing required fields: {", ".join(missing_fields)}'
        }), 400
    
    try:
        server = server_storage.create_server(data)
        return jsonify(server), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@server_bp.route('/servers/<server_id>', methods=['GET'])
def get_server_details(server_id):
    """Get details for a specific server.
    
    Args:
        server_id: Server ID
        
    Returns:
        Server object or 404 if not found
    """
    server = server_storage.get_server(server_id)
    
    if not server:
        return jsonify({'error': 'Server not found'}), 404
    
    return jsonify(_augment_with_runtime(server))


@server_bp.route('/servers/<server_id>/settings', methods=['PUT'])
def update_server_settings(server_id):
    """Update server settings.
    
    Args:
        server_id: Server ID
        
    Expected JSON body:
        Any server fields to update
        
    Returns:
        Updated server object or 404 if not found
    """
    data = request.get_json()
    
    if not data:
        return jsonify({'error': 'Request body is required'}), 400
    
    # Don't allow updating certain fields
    protected_fields = ['id', 'createdAt']
    for field in protected_fields:
        data.pop(field, None)
    
    server = server_storage.update_server(server_id, data)
    
    if not server:
        return jsonify({'error': 'Server not found'}), 404
    
    return jsonify(server)


@server_bp.route('/servers/<server_id>', methods=['DELETE'])
def delete_server_route(server_id):
    """Delete a server.
    
    Args:
        server_id: Server ID
        
    Returns:
        Success message or 404 if not found
    """
    success = server_storage.delete_server(server_id)
    
    if not success:
        return jsonify({'error': 'Server not found'}), 404
    
    return jsonify({
        'success': True,
        'message': 'Server deleted successfully'
    })


# Server control endpoints
@server_bp.route('/servers/<server_id>/start', methods=['POST'])
def start_server_by_id(server_id):
    """Start a specific server.
    
    Args:
        server_id: Server ID
        
    Returns:
        Success message with updated status
    """
    server = server_storage.get_server(server_id)
    if not server:
        return jsonify({'error': 'Server not found'}), 404

    try:
        result = process_registry.start_server(server)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    status_value = result.get('status')
    success = status_value == 'running'
    updated_server = (
        server_storage.update_server_status(server_id, status_value)
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
    """Stop a specific server.
    
    Args:
        server_id: Server ID
        
    Returns:
        Success message with updated status
    """
    server = server_storage.get_server(server_id)
    if not server:
        return jsonify({'error': 'Server not found'}), 404

    result = process_registry.stop_server(server_id)
    status_value = result.get('status')
    success = status_value == 'stopped'
    updated_server = (
        server_storage.update_server_status(server_id, status_value)
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
    """Restart a specific server.
    
    Args:
        server_id: Server ID
        
    Returns:
        Success message with updated status
    """
    server = server_storage.get_server(server_id)
    if not server:
        return jsonify({'error': 'Server not found'}), 404

    try:
        result = process_registry.restart_server(server)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    start_status = result['start'].get('status')
    success = start_status == 'running'
    updated_server = (
        server_storage.update_server_status(server_id, start_status)
        if start_status else server
    )

    response = {
        'success': success,
        'message': result['start'].get('message', ''),
        'details': result,
        'server': _augment_with_runtime(updated_server or server)
    }
    return jsonify(response), 200 if success else 400
