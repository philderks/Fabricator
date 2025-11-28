"""Flask application factory and shared extensions."""
from flask import Flask
from flask_cors import CORS

from backend.core.config import get_config
from backend.server.routes import server_bp
from backend.modrinth.routes import modrinth_bp


def create_app() -> Flask:
    """Create and configure the Flask application."""
    app = Flask(__name__)

    config = get_config()
    app.config.from_object(config)

    CORS(app)

    app.register_blueprint(server_bp)
    app.register_blueprint(modrinth_bp)
    return app
