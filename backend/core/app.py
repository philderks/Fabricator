"""Flask application factory and shared extensions."""
import os
import sys
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory
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


def _load_dotenv() -> None:
    """Load ``.env`` from project root (and optionally cwd)."""
    from dotenv import load_dotenv
    base = Path(get_base_path())
    load_dotenv(base / ".env")
    load_dotenv()


def create_app() -> Flask:
    """Create and configure the Flask application."""
    _load_dotenv()
    base_path = get_base_path()
    static_dir = Path(base_path) / "frontend" / "dist"
    static_folder_path = str(static_dir)

    app = Flask(__name__, static_folder=None)

    config = get_config()
    app.config.from_object(config)

    CORS(app, origins=config.CORS_ORIGINS)

    app.register_blueprint(server_bp)
    app.register_blueprint(modrinth_bp)
    app.register_blueprint(system_bp)

    # One-time startup cleanup: flip stale 'installing'/'starting' statuses
    # left over from a previous run. Tolerates a missing/malformed index.
    from backend.server.routes import cleanup_stale_statuses
    cleanup_stale_statuses()

    @app.route(
        "/api/<path:_>",
        methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    )
    def api_not_found(_):
        """Return JSON (not the SPA's HTML) for unknown /api/... paths."""
        return jsonify({"error": "endpoint not found", "path": request.path}), 404

    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def serve_frontend(path: str):
        """Serve Vue build files when available, otherwise warn the user."""

        index_file = Path(static_folder_path) / "index.html"
        requested = Path(static_folder_path) / path

        if path and requested.exists() and requested.is_file():
            return send_from_directory(static_folder_path, path)

        if index_file.exists():
            return send_from_directory(static_folder_path, "index.html")

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

