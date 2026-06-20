"""Built-in panel authentication.

Wires a single before_request gate and the auth blueprint into the app, and
enforces fail-closed startup: when auth is enabled but unconfigured, the app
refuses to start — in EVERY environment.
"""
from __future__ import annotations

from datetime import timedelta

from flask import current_app, jsonify, request, session

from backend.auth import service
from backend.auth.routes import auth_bp

# Endpoints reachable without a session when auth is enabled.
_PUBLIC_ENDPOINTS = frozenset(
    {
        ("POST", "/api/auth/login"),
        ("GET", "/api/auth/status"),
        ("GET", "/api/health"),
    }
)

_SESSION_LIFETIME = timedelta(days=7)


def _failclosed_message(missing: list[str]) -> str:
    joined = ", ".join(missing)
    return (
        "Built-in authentication is enabled but not configured; refusing to start.\n"
        f"Missing: {joined}.\n\n"
        "Set a stable signing key and a password hash, then restart:\n"
        "  1. SECRET_KEY    - a long random string, e.g.\n"
        '                     python -c "import secrets; print(secrets.token_hex(32))"\n'
        "  2. FABRICATOR_AUTH_PASSWORD_HASH - generate with EITHER:\n"
        "       fabricator hash-password          (systemd install)\n"
        "       python -m backend.auth hash       (Docker / running from source)\n\n"
        "To intentionally run without the built-in login (e.g. behind your own\n"
        "reverse-proxy auth), set FABRICATOR_DISABLE_AUTH=1."
    )


def _auth_gate():
    """Single default-deny gate for everything under /api/."""
    if request.method == "OPTIONS":
        return None  # CORS preflight
    if not request.path.startswith("/api/"):
        return None  # static frontend / login page
    if not current_app.config.get("FABRICATOR_AUTH_ENABLED"):
        return None  # explicit opt-out (FABRICATOR_DISABLE_AUTH)
    if (request.method, request.path) in _PUBLIC_ENDPOINTS:
        return None
    if session.get("authenticated") is True:
        return None
    return jsonify({"error": "authentication required"}), 401


def init_auth(app) -> None:
    """Configure auth on ``app``: session cookie, fail-closed validation,
    the gate, and the blueprint. Resolves the disable/secure flags ONCE here so
    startup validation and the gate read the same parsed values.
    """
    disabled = service.auth_disabled()

    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=service.cookie_secure(),
        PERMANENT_SESSION_LIFETIME=_SESSION_LIFETIME,
    )
    app.config["FABRICATOR_AUTH_ENABLED"] = not disabled

    if not disabled:
        missing: list[str] = []
        if not app.config.get("SECRET_KEY"):
            missing.append("SECRET_KEY")
        if not service.get_password_hash():
            missing.append("FABRICATOR_AUTH_PASSWORD_HASH")
        if missing:
            raise RuntimeError(_failclosed_message(missing))

    app.register_blueprint(auth_bp)
    app.before_request(_auth_gate)
