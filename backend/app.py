"""Flask application factory."""
from flask import Flask
from flask_cors import CORS

from backend.config import get_config
from backend.routes.server import server_bp
from backend.routes.modrinth import modrinth_bp


def create_app():
    """Create and configure the Flask application."""
    app = Flask(__name__)
    
    # Load configuration
    config = get_config()
    app.config.from_object(config)
    
    # Enable CORS
    CORS(app)
    
    # Register blueprints
    app.register_blueprint(server_bp)
    app.register_blueprint(modrinth_bp)
    
    return app
