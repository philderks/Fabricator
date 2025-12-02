"""Fabricator backend package.

This module exposes the application factory for the Fabricator desktop app.
"""
from pathlib import Path
from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS

from .api.routes import api_bp

BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIST = BASE_DIR / "frontend_dist"


def create_app() -> Flask:
    """Create and configure the Flask application.

    The app serves API routes under ``/api`` and the built Vue frontend
    from ``frontend_dist``. Unknown routes fall back to ``index.html`` to
    support client-side routing.
    """

    app = Flask(
        __name__,
        static_folder=str(FRONTEND_DIST),
        static_url_path="",
    )

    CORS(app)
    app.register_blueprint(api_bp)

    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def serve_frontend(path: str):
        """Serve the compiled frontend or fall back to ``index.html``.

        If the requested asset exists inside ``frontend_dist`` it is served
        directly; otherwise ``index.html`` is returned for SPA routing. When
        the frontend has not yet been built, a helpful JSON message is
        returned.
        """

        index_file = FRONTEND_DIST / "index.html"
        requested = FRONTEND_DIST / path

        if path and requested.exists() and requested.is_file():
            return send_from_directory(FRONTEND_DIST, path)

        if index_file.exists():
            return send_from_directory(FRONTEND_DIST, "index.html")

        return (
            jsonify(
                {
                    "error": "Frontend not built",
                    "detail": "Run the build script to generate frontend_dist.",
                }
            ),
            503,
        )

    return app
