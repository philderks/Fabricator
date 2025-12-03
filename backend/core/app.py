"""Flask application factory and shared extensions."""
from pathlib import Path
from flask import Flask
from flask_cors import CORS
from flask import Flask, send_from_directory, jsonify

from backend.core.config import get_config
from backend.server.routes import server_bp
from backend.modrinth.routes import modrinth_bp


BASE_DIR = Path(__file__).resolve().parent.parent  # backend/
FRONTEND_DIST = BASE_DIR.parent / "frontend" / "dist"


def create_app() -> Flask:
    """Create and configure the Flask application."""
    app = Flask(
        __name__,
        static_folder=str(FRONTEND_DIST),
        static_url_path="",
    )

    config = get_config()
    app.config.from_object(config)

    CORS(app)

    app.register_blueprint(server_bp)
    app.register_blueprint(modrinth_bp)

    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def serve_frontend(path: str):
        """
        Serve the compiled Vue frontend from frontend/dist.

        - Wenn eine angefragte Datei existiert -> direkt ausliefern (JS, CSS, Bilder).
        - Sonst -> index.html (damit der Vue-Router übernimmt).
        """
        index_file = FRONTEND_DIST / "index.html"
        requested = FRONTEND_DIST / path

        if path and requested.exists() and requested.is_file():
            return send_from_directory(FRONTEND_DIST, path)

        if index_file.exists():
            return send_from_directory(FRONTEND_DIST, "index.html")

        # Falls noch kein Build vorhanden ist
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

