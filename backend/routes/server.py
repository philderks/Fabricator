"""Server management routes."""
from flask import Blueprint, jsonify

from backend.services.server_manager import ServerManager

server_bp = Blueprint('server', __name__, url_prefix='/api')
server_manager = ServerManager()


@server_bp.route('/status', methods=['GET'])
def get_status():
    """Return the current status of the managed server."""
    status = server_manager.status()
    status.update({"version": "1.0.0"})
    return jsonify(status)


@server_bp.route('/start', methods=['POST'])
def start_server():
    """Start the managed server process."""
    result = server_manager.start()
    return jsonify(result)


@server_bp.route('/stop', methods=['POST'])
def stop_server():
    """Stop the managed server process."""
    result = server_manager.stop()
    return jsonify(result)


@server_bp.route('/health', methods=['GET'])
def health_check():
    """Simple health check endpoint."""
    return jsonify({'healthy': True})
