from flask import Flask, jsonify, request
from flask_cors import CORS
import os

from server_service import ServerService

app = Flask(__name__)
CORS(app)

server_service = ServerService()


@app.route('/api/status', methods=['GET'])
def get_status():
    """Return the current status of the managed server."""
    status = server_service.status()
    status.update({"version": "1.0.0"})
    return jsonify(status)


@app.route('/api/start', methods=['POST'])
def start_server():
    """Start the managed server process."""
    command = request.json.get("command") if request.is_json else None
    if command:
        server_service.command = command
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


if __name__ == '__main__':
    debug_mode = os.environ.get('FLASK_ENV') != 'production'
    app.run(debug=debug_mode, host='0.0.0.0', port=5000)
