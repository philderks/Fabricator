"""Authentication endpoints: setup, login, logout, status.

SENSITIVE: the setup/login handlers receive the operator password. Never log
the request body, the password, or the configured hash.
"""
from __future__ import annotations

import time

from flask import Blueprint, current_app, jsonify, request, session

from backend.auth import service

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")

# Minimal brute-force friction only (no lockout / IP tracking). Tests set this
# to 0 to avoid the real delay.
LOGIN_FAILURE_DELAY_SECONDS = 1.0

# First-boot setup password floor. Single operator — one field, no policy zoo.
MIN_PASSWORD_LENGTH = 8


def _login_session() -> None:
    """Mark the current session authenticated (fixation-safe: clear first)."""
    session.clear()
    session["authenticated"] = True
    session.permanent = True


@auth_bp.route("/setup", methods=["POST"])
def setup():
    """First-boot: set the operator password (reachable ONLY in setup mode).

    JSON only (``application/json``) — a non-JSON / form-encoded body is
    rejected, which together with the CORS preflight closes pre-auth CSRF on
    this state-changing endpoint. One-time: refuses (409) once any credential
    exists, guarded both by the runtime ``FABRICATOR_NEEDS_SETUP`` flag and the
    race-safe ``service.complete_setup`` exists-check.
    """
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "JSON body required"}), 400
    password = data.get("password")
    if not isinstance(password, str) or len(password) < MIN_PASSWORD_LENGTH:
        return (
            jsonify(
                {"error": f"password must be at least {MIN_PASSWORD_LENGTH} characters"}
            ),
            400,
        )

    if not current_app.config.get("FABRICATOR_NEEDS_SETUP"):
        return jsonify({"error": "already configured"}), 409

    # Race-safe one-time write: complete_setup returns False if a credential
    # already exists (defends against races / a stale NEEDS_SETUP flag).
    if not service.complete_setup(password):
        current_app.config["FABRICATOR_NEEDS_SETUP"] = False
        return jsonify({"error": "already configured"}), 409

    current_app.config["FABRICATOR_NEEDS_SETUP"] = False
    _login_session()
    return jsonify({"authenticated": True}), 200


@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    password = data.get("password")
    if not password or not isinstance(password, str):
        return jsonify({"error": "password required"}), 400
    if not service.verify_password(password):
        time.sleep(LOGIN_FAILURE_DELAY_SECONDS)
        return jsonify({"error": "invalid credentials"}), 401
    _login_session()
    return jsonify({"authenticated": True}), 200


@auth_bp.route("/change-password", methods=["POST"])
def change_password():
    """Change the operator password (requires the CURRENT password).

    Protected by the gate (session required). Re-verifies the current password
    so a hijacked session can't silently lock out the operator. JSON only.
    Refuses (409) when the password is declared via the env var. SENSITIVE:
    never log either password.
    """
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "JSON body required"}), 400
    current = data.get("current")
    new = data.get("new")
    if not isinstance(current, str) or not isinstance(new, str):
        return jsonify({"error": "current and new passwords are required"}), 400
    if len(new) < MIN_PASSWORD_LENGTH:
        return (
            jsonify(
                {"error": f"password must be at least {MIN_PASSWORD_LENGTH} characters"}
            ),
            400,
        )
    if service.password_is_env_managed():
        return (
            jsonify(
                {
                    "error": "password is set via FABRICATOR_AUTH_PASSWORD_HASH; "
                    "change it there"
                }
            ),
            409,
        )
    if not service.verify_password(current):
        time.sleep(LOGIN_FAILURE_DELAY_SECONDS)
        return jsonify({"error": "current password is incorrect"}), 401
    service.set_password(new)
    return jsonify({"changed": True}), 200


@auth_bp.route("/logout", methods=["POST"])
def logout():
    # Reaching here means the gate already let us through (logout is protected).
    session.clear()
    return jsonify({"authenticated": False}), 200


@auth_bp.route("/status", methods=["GET"])
def status():
    enabled = bool(current_app.config.get("FABRICATOR_AUTH_ENABLED"))
    needs_setup = bool(current_app.config.get("FABRICATOR_NEEDS_SETUP"))
    authenticated = (
        enabled and not needs_setup and session.get("authenticated") is True
    )
    return (
        jsonify(
            {"enabled": enabled, "authenticated": authenticated, "needs_setup": needs_setup}
        ),
        200,
    )
