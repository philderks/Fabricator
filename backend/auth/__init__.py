"""Built-in panel authentication.

Wires a single before_request gate and the auth blueprint into the app.

State model (no fail-closed-on-missing-credential anymore):
  - FABRICATOR_DISABLE_AUTH truthy  -> disabled; the gate passes everything.
  - else, credential resolved (env hash > persisted file):
      * present -> CONFIGURED (normal login).
      * absent  -> SETUP MODE: the app boots locked, serving only the setup
        page + status + health until a password is set via /api/auth/setup.
The only remaining hard-fail is an un-writable data dir (setup can't persist).
"""
from __future__ import annotations

from datetime import timedelta

from flask import current_app, jsonify, request, session

from backend.auth import service
from backend.auth.routes import auth_bp

# Reachable without a session when CONFIGURED.
_PUBLIC_ENDPOINTS = frozenset(
    {
        ("POST", "/api/auth/login"),
        ("GET", "/api/auth/status"),
        ("GET", "/api/health"),
    }
)

# Reachable in SETUP MODE (hard lockdown — nothing else). Health stays open so
# container/k8s health probes don't restart-loop during the setup window.
_SETUP_ENDPOINTS = frozenset(
    {
        ("POST", "/api/auth/setup"),
        ("GET", "/api/auth/status"),
        ("GET", "/api/health"),
    }
)

_SESSION_LIFETIME = timedelta(days=7)


def _unwritable_message(path) -> str:
    return (
        "Fabricator's data directory is not writable, so the login credential "
        f"and session key cannot be persisted:\n  {path}\n\n"
        "Fix the directory's permissions/ownership and restart. (Under systemd "
        "this is /var/lib/fabricator, owned by the 'fabricator' user.) To run "
        "without the built-in login, set FABRICATOR_DISABLE_AUTH=1."
    )


def _auth_gate():
    """Single default-deny gate for everything under /api/."""
    if request.method == "OPTIONS":
        return None  # CORS preflight
    if not request.path.startswith("/api/"):
        return None  # static frontend / SPA (setup & login pages)
    if not current_app.config.get("FABRICATOR_AUTH_ENABLED"):
        return None  # explicit opt-out (FABRICATOR_DISABLE_AUTH)

    if current_app.config.get("FABRICATOR_NEEDS_SETUP"):
        # Locked setup mode: only the setup page may write the first credential.
        if (request.method, request.path) in _SETUP_ENDPOINTS:
            return None
        return jsonify({"error": "setup required"}), 401

    # Configured: public allowlist, else require a session.
    if (request.method, request.path) in _PUBLIC_ENDPOINTS:
        return None
    if session.get("authenticated") is True:
        return None
    return jsonify({"error": "authentication required"}), 401


def init_auth(app) -> None:
    """Configure auth on ``app``: session cookie, credential/key resolution,
    the gate, and the blueprint.

    ``FABRICATOR_DISABLE_AUTH`` is resolved once here (the gate reads the stored
    value). ``FABRICATOR_NEEDS_SETUP`` is seeded here but is runtime-mutable —
    the setup handler flips it to False once a password is set.
    """
    disabled = service.auth_disabled()

    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=service.cookie_secure(),
        PERMANENT_SESSION_LIFETIME=_SESSION_LIFETIME,
    )
    app.config["FABRICATOR_AUTH_ENABLED"] = not disabled

    if disabled:
        app.config["FABRICATOR_NEEDS_SETUP"] = False
    else:
        # Persisting the key/credential needs a writable data dir — the only
        # remaining hard-fail (setup mode is pointless if it can't persist).
        if not service.data_dir_writable():
            raise RuntimeError(_unwritable_message(service.data_dir()))
        # SECRET_KEY: env override, else load-or-generate-and-persist. Set into
        # app.config before any request is served.
        app.config["SECRET_KEY"] = service.load_or_create_secret_key()
        # Setup mode iff no credential is configured yet (env or file).
        app.config["FABRICATOR_NEEDS_SETUP"] = service.get_password_hash() is None

    app.register_blueprint(auth_bp)
    app.before_request(_auth_gate)
