"""Example API routes for the Fabricator backend."""
from datetime import datetime
from flask import Blueprint, jsonify

api_bp = Blueprint("api", __name__, url_prefix="/api")


@api_bp.get("/status")
def status():
    """Return a simple status payload for the UI."""

    return jsonify(
        {
            "status": "ok",
            "message": "Fabricator backend is running",
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }
    )


@api_bp.get("/health")
def health():
    """Health check endpoint."""

    return jsonify({"healthy": True})
