"""Authentication endpoints: login, logout, status.

SENSITIVE: the login handler receives the operator password. Never log the
request body, the password, or the configured hash.
"""
from __future__ import annotations

import time

from flask import Blueprint, current_app, jsonify, request, session

from backend.auth import service

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")

# Minimal brute-force friction only (no lockout / IP tracking). Tests set this
# to 0 to avoid the real delay.
LOGIN_FAILURE_DELAY_SECONDS = 1.0


@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    password = data.get("password")
    if not password or not isinstance(password, str):
        return jsonify({"error": "password required"}), 400
    if not service.verify_password(password):
        time.sleep(LOGIN_FAILURE_DELAY_SECONDS)
        return jsonify({"error": "invalid credentials"}), 401
    session.clear()
    session["authenticated"] = True
    session.permanent = True
    return jsonify({"authenticated": True}), 200


@auth_bp.route("/logout", methods=["POST"])
def logout():
    # Reaching here means the gate already let us through (logout is protected).
    session.clear()
    return jsonify({"authenticated": False}), 200


@auth_bp.route("/status", methods=["GET"])
def status():
    enabled = bool(current_app.config.get("FABRICATOR_AUTH_ENABLED"))
    authenticated = enabled and session.get("authenticated") is True
    return jsonify({"enabled": enabled, "authenticated": authenticated}), 200
