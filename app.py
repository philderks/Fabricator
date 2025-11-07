from flask import Flask, jsonify
from flask_cors import CORS
import os

app = Flask(__name__)
CORS(app)

@app.route('/api/status', methods=['GET'])
def get_status():
    """
    Returns the current status of the Minecraft server.
    This is a placeholder endpoint that can be expanded later.
    """
    return jsonify({
        'status': 'offline',
        'message': 'Minecraft server manager is ready',
        'version': '1.0.0'
    })

@app.route('/api/health', methods=['GET'])
def health_check():
    """Simple health check endpoint."""
    return jsonify({'healthy': True})

if __name__ == '__main__':
    # Development mode - set FLASK_ENV=production in production environments
    debug_mode = os.environ.get('FLASK_ENV') != 'production'
    app.run(debug=debug_mode, host='0.0.0.0', port=5000)
