"""Authentication policy + credential helpers (pure, Flask-free).

SENSITIVE: the operator password and its hash pass through here. Never log,
repr, or place them in exception messages.
"""
from __future__ import annotations

import os

from werkzeug.security import check_password_hash, generate_password_hash

from backend.utils.strings import bool_from_str

_PASSWORD_HASH_ENV = "FABRICATOR_AUTH_PASSWORD_HASH"
_DISABLE_ENV = "FABRICATOR_DISABLE_AUTH"
_COOKIE_SECURE_ENV = "FABRICATOR_SESSION_COOKIE_SECURE"


def auth_disabled() -> bool:
    """Return True only for an explicit opt-out (fail-safe).

    Uses the shared allowlist parser ``bool_from_str`` (``1/true/yes/on``,
    case-insensitive). Everything else - ``"0"``, ``"false"``, empty, unset -
    keeps auth ENABLED. This flag turns off ALL authentication, so the default
    must be fail-safe.
    """
    return bool_from_str(os.environ.get(_DISABLE_ENV))


def cookie_secure() -> bool:
    """Return True when the session cookie should carry the ``Secure`` flag."""
    return bool_from_str(os.environ.get(_COOKIE_SECURE_ENV))


def get_password_hash() -> str | None:
    """Return the configured password hash, or None when unset/empty.

    SENSITIVE: the returned value is a credential hash - do not log or repr.
    """
    return os.environ.get(_PASSWORD_HASH_ENV) or None


def hash_password(password: str) -> str:
    """Return a Werkzeug hash of ``password`` (to put in the env var).

    Wraps ``generate_password_hash`` — the single place to change the hashing
    scheme later (e.g. argon2) without touching callers.
    """
    return generate_password_hash(password)


def verify_password(password: str) -> bool:
    """Return True when ``password`` matches the configured hash.

    Constant-time via ``check_password_hash``. Returns False (never raises)
    when no hash is configured or the configured hash is malformed.
    SENSITIVE: do not log inputs.
    """
    stored = get_password_hash()
    if not stored:
        return False
    try:
        return check_password_hash(stored, password)
    except ValueError:
        # Malformed hash in the env (e.g. plaintext) → treat as auth failure,
        # never a 500. SENSITIVE: the offending value is not logged.
        return False
