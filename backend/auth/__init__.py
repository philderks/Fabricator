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

from backend.auth import buckets, service
from backend.auth.routes import auth_bp
from backend.managed import is_managed

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


def _bearer_decision(credential: str):
    """Resolve an MCP bearer-token request against the route permission table.

    Returns ``None`` to ALLOW only when the token is valid AND the route is in
    scope; otherwise returns a rejection response. This is the EXCLUSIVE
    resolution: the caller invokes it whenever an ``Authorization: Bearer``
    header is present, and it never falls back to the session.

    401 = authentication (switch off, invalid/malformed token); 403 =
    authorization (valid token, but the route is NEVER / unknown / out of the
    token's scope).

    SECURITY: the switch and token map are read FRESH from auth.json on every
    call (``service.mcp_state``). Do NOT add a TTL cache, module-level memo, or
    app.config snapshot here — the off-switch and token revocation must take
    effect live.
    """
    state = service.mcp_state()
    if not state["enabled"]:
        return jsonify({"error": "mcp token auth disabled"}), 401
    match = service.match_token(state["tokens"], credential)
    if match is None:
        return jsonify({"error": "invalid token"}), 401
    _token_id, scope = match
    rule = request.url_rule
    if rule is None:
        # 405 / redirect / no matched rule: nothing to bucket -> fail closed.
        return jsonify({"error": "forbidden for token"}), 403
    method = "GET" if request.method == "HEAD" else request.method
    bucket = buckets.BUCKETS.get((method, rule.rule))
    if bucket is None or bucket == "never":
        return jsonify({"error": "forbidden for token"}), 403
    if bucket == "manage" and scope != "manage":
        return jsonify({"error": "insufficient scope"}), 403
    return None  # read route (any scope) or manage route with a manage token


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

    # MCP API token: an Authorization: Bearer header makes this a token request,
    # resolved here and NEVER falling back to the session. Placed BELOW the
    # DISABLE_AUTH opt-out (so it never runs on an auth-off / fleet box) and
    # ABOVE the public allowlist + session check. The scheme is matched
    # case-insensitively; a present-but-empty Bearer is still a token request
    # (rejected), so it cannot slip through to the session.
    scheme, _, credential = request.headers.get("Authorization", "").partition(" ")
    if scheme.lower() == "bearer":
        return _bearer_decision(credential.strip())

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
    # Managed-hosting flag, exposed to the SPA via GET /api/auth/status. Read
    # once here alongside the auth flags; off for every self-host install.
    app.config["FABRICATOR_MANAGED"] = is_managed()

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
