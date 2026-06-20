"""Authentication policy + credential helpers.

SENSITIVE: the operator password, its hash, and the session SECRET_KEY pass
through here. Never log, repr, or place them in exception messages.

Persistence: a single 0600 ``auth.json`` co-located with ``servers.json`` (the
same persistent data dir — ``/var/lib/fabricator`` under the systemd service,
``~/.fabricator`` in dev, a temp dir in tests). It holds ``secret_key`` and
``password_hash``. Environment variables override the file independently:
``SECRET_KEY`` and ``FABRICATOR_AUTH_PASSWORD_HASH`` (precedence: env > file).
"""
from __future__ import annotations

import json
import os
import secrets
import threading
from pathlib import Path

from werkzeug.security import check_password_hash, generate_password_hash

from backend.utils.strings import bool_from_str

_PASSWORD_HASH_ENV = "FABRICATOR_AUTH_PASSWORD_HASH"
_SECRET_KEY_ENV = "SECRET_KEY"
_DISABLE_ENV = "FABRICATOR_DISABLE_AUTH"
_COOKIE_SECURE_ENV = "FABRICATOR_SESSION_COOKIE_SECURE"

_AUTH_FILE_NAME = "auth.json"

# Guards the read-modify-write of auth.json. Reentrant so the one-time
# ``complete_setup`` can call ``set_password`` without self-deadlock. The app is
# a single (threaded) process, so a process-local lock is sufficient.
_lock = threading.RLock()


# --------------------------------------------------------------------------- #
# Flag parsing (fail-safe)
# --------------------------------------------------------------------------- #

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


# --------------------------------------------------------------------------- #
# Persistent state file (0600, co-located with servers.json)
# --------------------------------------------------------------------------- #

def _auth_file() -> Path:
    """Path to ``auth.json`` in the same data dir as ``servers.json``.

    Derived from the live config so it tracks the prod override
    (``/var/lib/fabricator``) and test redirection (``SERVER_INDEX_FILE``)
    automatically — never a user-home path under the systemd service.
    """
    from backend.core.config import get_config  # lazy: keep pure helpers light
    return Path(get_config().SERVERS_FILE).parent / _AUTH_FILE_NAME


def _read_auth_file() -> dict:
    """Return the parsed ``auth.json`` as a dict, or ``{}`` if absent/unreadable.

    SENSITIVE: the returned dict may hold the hash and secret key — do not log.
    """
    try:
        with open(_auth_file(), "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (FileNotFoundError, ValueError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_auth_file(data: dict) -> None:
    """Atomically persist ``data`` to ``auth.json`` with 0600 permissions.

    Creates a 0600 ``.tmp`` from the start (no world-readable window), fsyncs,
    then ``os.replace``s it into place — the same atomic discipline as
    ``server/storage.py``. SENSITIVE: contents are secrets; never logged. On
    Windows the mode bits are best-effort; the per-user data dir is the real
    protection there.
    """
    path = _auth_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    try:
        os.chmod(path, 0o600)
    except OSError:  # best-effort on platforms without POSIX modes
        pass


def data_dir_writable() -> bool:
    """True if the ``auth.json`` directory is writable (or creatable).

    The single remaining hard-fail at startup: setup mode is pointless if the
    credential/key cannot be persisted. Probes the nearest existing ancestor.
    """
    probe = _auth_file().parent
    while not probe.exists():
        parent = probe.parent
        if parent == probe:
            break
        probe = parent
    return os.access(probe, os.W_OK)


# --------------------------------------------------------------------------- #
# Credential
# --------------------------------------------------------------------------- #

def get_password_hash() -> str | None:
    """Return the configured password hash: env override > file > None.

    SENSITIVE: the returned value is a credential hash - do not log or repr.
    """
    env = os.environ.get(_PASSWORD_HASH_ENV)
    if env:
        return env
    return _read_auth_file().get("password_hash") or None


def hash_password(password: str) -> str:
    """Return a Werkzeug hash of ``password``.

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
        # Malformed hash (e.g. plaintext in the env) → auth failure, not a 500.
        return False


def set_password(password: str) -> None:
    """Persist a new password hash to ``auth.json``, preserving ``secret_key``.

    Read-modify-write under the lock so the persisted SECRET_KEY is never
    clobbered (otherwise sessions would be invalidated on the next restart).
    SENSITIVE: never log the password or hash.
    """
    new_hash = hash_password(password)
    with _lock:
        data = _read_auth_file()
        data["password_hash"] = new_hash
        _write_auth_file(data)


def complete_setup(password: str) -> bool:
    """Set the first password iff none exists yet — the one-time guard.

    Returns True when this call persisted the password, False when a credential
    already existed (env or file). Race-safe via the lock, so two concurrent
    first-boot requests cannot both succeed.
    """
    with _lock:
        if get_password_hash() is not None:
            return False
        set_password(password)
        return True


# --------------------------------------------------------------------------- #
# Session signing key
# --------------------------------------------------------------------------- #

def load_or_create_secret_key() -> str:
    """Return the session SECRET_KEY: env override > file > generate+persist.

    On first boot with no env key and no file, a random key is generated and
    persisted (0600) so sessions survive restarts. SENSITIVE: never log.
    """
    env = os.environ.get(_SECRET_KEY_ENV)
    if env:
        return env
    with _lock:
        data = _read_auth_file()
        key = data.get("secret_key")
        if key:
            return key
        key = secrets.token_hex(32)
        data["secret_key"] = key
        _write_auth_file(data)
        return key
