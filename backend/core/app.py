"""Flask application factory and shared extensions."""
import os
import sys
from pathlib import Path

from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS

from backend.core.config import get_config
from backend.server.routes import server_bp
from backend.modrinth.routes import modrinth_bp
from backend.system.routes import system_bp

def get_base_path() -> str:
    """Return base path that works in dev and when frozen with PyInstaller."""
    if getattr(sys, 'frozen', False):
        return sys._MEIPASS  # type: ignore[attr-defined]
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def create_app() -> Flask:
    """Create and configure the Flask application."""
    base_path = get_base_path()
    static_dir = Path(base_path) / "frontend" / "dist"

    app = Flask(
        __name__,
        static_folder=str(static_dir),
        static_url_path="",
    )

    config = get_config()
    app.config.from_object(config)

    CORS(app)

    app.register_blueprint(server_bp)
    app.register_blueprint(modrinth_bp)
    app.register_blueprint(system_bp)

    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def serve_frontend(path: str):
        """Serve Vue build files when available, otherwise warn the user."""

        index_file = Path(app.static_folder) / "index.html"
        requested = Path(app.static_folder) / path

        if path and requested.exists() and requested.is_file():
            return send_from_directory(app.static_folder, path)

        if index_file.exists():
            return send_from_directory(app.static_folder, "index.html")

        return (
            jsonify(
                {
                    "error": "Frontend not built",
                    "detail": "Run `npm run build` in the frontend folder.",
                }
            ),
            503,
        )

    return app

