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

import hashlib
import json
import logging
import os
import re
import secrets
import threading
import time
from pathlib import Path

from werkzeug.security import check_password_hash, generate_password_hash

from backend.utils.strings import bool_from_str
from backend.utils.time import iso_z_now

log = logging.getLogger(__name__)

_PASSWORD_HASH_ENV = "FABRICATOR_AUTH_PASSWORD_HASH"
_SECRET_KEY_ENV = "SECRET_KEY"
_DISABLE_ENV = "FABRICATOR_DISABLE_AUTH"
_COOKIE_SECURE_ENV = "FABRICATOR_SESSION_COOKIE_SECURE"

_AUTH_FILE_NAME = "auth.json"

# Set in auth.json when the operator turns the password off from the UI. This
# has to be recorded explicitly rather than inferred from a missing
# password_hash: "no credential" already means "first boot, run setup", so
# deleting the hash alone would put the app into setup mode on the next start
# and demand a new password instead of staying open.
_AUTH_DISABLED_KEY = "auth_disabled"

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

def data_dir() -> Path:
    """The persistent data directory — the same one ``servers.json`` uses.

    Derived from the live config so it tracks the prod override
    (``/var/lib/fabricator``) and test redirection (``SERVER_INDEX_FILE``)
    automatically — never a user-home path under the systemd service.
    """
    from backend.core.config import get_config  # lazy: keep pure helpers light
    return Path(get_config().SERVERS_FILE).parent


def _auth_file() -> Path:
    """Path to the 0600 ``auth.json`` state file in the data dir."""
    return data_dir() / _AUTH_FILE_NAME


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
    probe = data_dir()
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


def password_is_env_managed() -> bool:
    """True when the password hash comes from the env var.

    In that mode the credential is declarative; a UI password change can't take
    effect (env overrides the file), so the change-password endpoint refuses.
    """
    return bool(os.environ.get(_PASSWORD_HASH_ENV))


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


def password_disabled_in_file() -> bool:
    """True when the operator turned the password off from the UI.

    Distinct from ``auth_disabled()``, which reads the env opt-out. Fail-safe
    like everything else here: an absent or unreadable file means NOT disabled.
    """
    return bool(_read_auth_file().get(_AUTH_DISABLED_KEY))


def disable_password() -> None:
    """Drop the stored credential and record the operator's opt-out.

    The hash is removed as well as flagged: leaving a stale credential behind
    would silently come back into force if the flag were ever cleared.
    SENSITIVE: never log the removed hash.
    """
    with _lock:
        data = _read_auth_file()
        data.pop("password_hash", None)
        data[_AUTH_DISABLED_KEY] = True
        _write_auth_file(data)


def set_password(password: str) -> None:
    """Persist a new password hash to ``auth.json``, preserving ``secret_key``.

    Read-modify-write under the lock so the persisted SECRET_KEY is never
    clobbered (otherwise sessions would be invalidated on the next restart).
    Also clears the opt-out flag: a stored credential and "password disabled"
    are mutually exclusive, so setting one is what turns auth back on.
    SENSITIVE: never log the password or hash.
    """
    new_hash = hash_password(password)
    with _lock:
        data = _read_auth_file()
        data["password_hash"] = new_hash
        data.pop(_AUTH_DISABLED_KEY, None)
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


# --------------------------------------------------------------------------- #
# MCP integration (the switch + API-token store)
# --------------------------------------------------------------------------- #
#
# Persisted as a single ``mcp`` block inside the same 0600 ``auth.json``:
#
#     "mcp": {
#         "enabled": <bool>,
#         "tokens": { "<id>": {"name", "scope", "hash", "created_at",
#                              "last_used_at"} }
#     }
#
# The switch and the token map are read fresh on every bearer-authenticated
# request (see ``backend/auth/__init__.py``) so the off-switch and revocation
# take effect live — deliberately un-cached.

_MCP_KEY = "mcp"


def _normalize_mcp(data: dict) -> dict:
    """Return ``data``'s ``mcp`` block as a well-formed ``{enabled, tokens}``.

    Fail-safe: a missing or malformed block yields the OFF, no-tokens default,
    so an unreadable/absent block never enables token auth. SENSITIVE: token
    entries hold secret hashes; never log the return value.
    """
    block = data.get(_MCP_KEY)
    if not isinstance(block, dict):
        return {"enabled": False, "tokens": {}}
    tokens = block.get("tokens")
    if not isinstance(tokens, dict):
        tokens = {}
    return {"enabled": bool(block.get("enabled")), "tokens": tokens}


def mcp_state() -> dict:
    """Return the current MCP switch + token map, read FRESH from ``auth.json``.

    Called on every bearer request; intentionally un-cached so the switch and
    token revocation are live. SENSITIVE: the token map holds secret hashes.
    """
    return _normalize_mcp(_read_auth_file())


def set_mcp_enabled(enabled: bool) -> None:
    """Persist the MCP on/off switch, preserving tokens + credential + key.

    Read-modify-write under the lock (the whole file is rewritten atomically),
    so a concurrent password change or token mint is never clobbered.
    """
    with _lock:
        data = _read_auth_file()
        block = data.get(_MCP_KEY)
        if not isinstance(block, dict):
            block = {}
        block["enabled"] = bool(enabled)
        block.setdefault("tokens", {})
        data[_MCP_KEY] = block
        _write_auth_file(data)


# --------------------------------------------------------------------------- #
# MCP API tokens
# --------------------------------------------------------------------------- #
#
# Token wire format: ``fab_<id>_<secret>``.
#   * ``id``     — a non-secret lookup key (hex), also shown in the UI.
#   * ``secret`` — 256 bits from ``secrets``; only its sha256 is persisted.
# A fast hash (sha256, no KDF) is correct here: the secret is high-entropy, so
# brute force is infeasible and a per-request KDF scan across all tokens is
# avoided. The presented secret is compared in constant time.

_TOKEN_PREFIX = "fab"
_TOKEN_SCOPES = ("read", "manage")
_MAX_TOKENS = 25
_TOKEN_NAME_RE = re.compile(r"^[A-Za-z0-9 ._-]{1,64}$")


class TokenLimitReached(Exception):
    """Raised by ``create_token`` when the per-install token cap is reached."""


def _validate_token_name(name) -> str:
    """Return the trimmed name, or raise ``ValueError`` if not display-safe."""
    cleaned = name.strip() if isinstance(name, str) else ""
    if not _TOKEN_NAME_RE.match(cleaned):
        raise ValueError(
            "token name must be 1-64 characters of letters, digits, spaces, "
            "'.', '_' or '-'"
        )
    return cleaned


def _validate_token_scope(scope) -> str:
    """Return the scope, or raise ``ValueError`` for anything but read/manage."""
    if scope not in _TOKEN_SCOPES:
        raise ValueError(f"scope must be one of {_TOKEN_SCOPES}")
    return scope


def _hash_secret(secret: str) -> str:
    """Return the hex sha256 of a token secret (the persisted form)."""
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def create_token(name: str, scope: str) -> dict:
    """Mint an MCP token; return its metadata PLUS the one-time full token.

    The returned ``token`` (``fab_<id>_<secret>``) is the ONLY time the secret
    is available — only its sha256 is stored. Raises ``ValueError`` on a bad
    name/scope and ``TokenLimitReached`` at the cap. Read-modify-write under
    the lock so a concurrent password change is never clobbered. SENSITIVE:
    never log the returned ``token``.
    """
    name = _validate_token_name(name)
    scope = _validate_token_scope(scope)
    with _lock:
        data = _read_auth_file()
        block = data.get(_MCP_KEY)
        if not isinstance(block, dict):
            block = {}
        tokens = block.get("tokens")
        if not isinstance(tokens, dict):
            tokens = {}
        if len(tokens) >= _MAX_TOKENS:
            raise TokenLimitReached(f"token limit reached ({_MAX_TOKENS})")
        token_id = secrets.token_hex(8)
        while token_id in tokens:  # collision is astronomically unlikely; still checked
            token_id = secrets.token_hex(8)
        secret = secrets.token_urlsafe(32)  # 256 bits
        created = iso_z_now()
        tokens[token_id] = {
            "name": name,
            "scope": scope,
            "hash": _hash_secret(secret),
            "created_at": created,
            "last_used_at": None,
        }
        block["tokens"] = tokens
        block.setdefault("enabled", False)
        data[_MCP_KEY] = block
        _write_auth_file(data)
    return {
        "id": token_id,
        "name": name,
        "scope": scope,
        "created_at": created,
        "last_used_at": None,
        "token": f"{_TOKEN_PREFIX}_{token_id}_{secret}",
    }


def match_token(tokens: dict, credential: str):
    """Resolve a presented ``fab_<id>_<secret>`` against ``tokens``.

    Returns ``(token_id, scope)`` on a valid match, else ``None``. Pure (no
    I/O): the caller passes the token map from ``mcp_state()``. A malformed
    credential fails closed; the secret is compared in constant time.
    """
    if not isinstance(credential, str):
        return None
    parts = credential.split("_", 2)
    if len(parts) != 3 or parts[0] != _TOKEN_PREFIX:
        return None
    token_id, secret = parts[1], parts[2]
    if not token_id or not secret:
        return None
    entry = tokens.get(token_id)
    if not isinstance(entry, dict):
        return None
    stored = entry.get("hash")
    if not isinstance(stored, str):
        return None
    if not secrets.compare_digest(_hash_secret(secret), stored):
        return None
    scope = entry.get("scope")
    if scope not in _TOKEN_SCOPES:
        return None
    return token_id, scope


def revoke_token(token_id: str) -> bool:
    """Delete a token by id. Returns ``True`` iff it existed."""
    with _lock:
        data = _read_auth_file()
        block = data.get(_MCP_KEY)
        if not isinstance(block, dict):
            return False
        tokens = block.get("tokens")
        if not isinstance(tokens, dict) or token_id not in tokens:
            return False
        del tokens[token_id]
        block["tokens"] = tokens
        data[_MCP_KEY] = block
        _write_auth_file(data)
        return True


def list_tokens() -> list:
    """Return token METADATA (never the secret hash), oldest first.

    Each item: ``{id, name, scope, created_at, last_used_at}``.
    """
    tokens = mcp_state()["tokens"]
    out = []
    for token_id, entry in tokens.items():
        if not isinstance(entry, dict):
            continue
        out.append(
            {
                "id": token_id,
                "name": entry.get("name"),
                "scope": entry.get("scope"),
                "created_at": entry.get("created_at"),
                "last_used_at": entry.get("last_used_at"),
            }
        )
    out.sort(key=lambda t: (t.get("created_at") or "", t.get("id") or ""))
    return out


# --------------------------------------------------------------------------- #
# Token last-used tracking (write-side only)
# --------------------------------------------------------------------------- #
#
# A5 — WRITE-SIDE ONLY. These in-memory buffers are NEVER consulted for an
# authentication or authorization decision. The bearer path always reads the
# switch and token map FRESH from auth.json (see backend/auth/__init__.py); this
# buffer exists solely to throttle how often last_used_at is written to disk. Do
# NOT turn it into a read cache.
_last_used_buffer: dict = {}   # token_id -> newest last-used ISO not yet persisted
_last_flush_at: dict = {}      # token_id -> monotonic seconds of its last persist
_FLUSH_INTERVAL_S = 60.0       # persist a given token's last_used at most this often


def _now_monotonic() -> float:
    """Monotonic clock read (indirected so tests can control the throttle)."""
    return time.monotonic()


def reset_for_tests() -> None:
    """Clear the in-memory last-used buffers (test isolation)."""
    _last_used_buffer.clear()
    _last_flush_at.clear()


def _flush_last_used_locked() -> set:
    """Persist buffered last_used_at values; return the ids actually written.

    Caller MUST hold ``_lock``. Whole-dict read-modify-write (re-reads the file
    inside the lock, then atomic ``tmp + os.replace`` via ``_write_auth_file``),
    so it never clobbers a concurrent password/key/token change. A buffered id
    that is no longer present in the file (revoked) is DROPPED — never written,
    never resurrected. The buffer is ALWAYS drained (``finally``), even if the
    write raises, so it can never grow unbounded; a write error propagates to
    the caller (``touch_token_last_used``), which degrades it to a logged no-op.
    """
    flushed = set()
    if not _last_used_buffer:
        return flushed
    try:
        data = _read_auth_file()
        block = data.get(_MCP_KEY)
        tokens = block.get("tokens") if isinstance(block, dict) else None
        if isinstance(tokens, dict):
            for token_id, ts in _last_used_buffer.items():
                entry = tokens.get(token_id)
                if isinstance(entry, dict):
                    entry["last_used_at"] = ts
                    flushed.add(token_id)
            if flushed:
                _write_auth_file(data)
    finally:
        _last_used_buffer.clear()  # drain regardless -> bounded even on failure
    return flushed


def touch_token_last_used(token_id: str) -> None:
    """Record that ``token_id`` was just used on an accepted request.

    Persists ``last_used_at`` to auth.json at most once per minute per token;
    between flushes the value is buffered, so the stored timestamp (and the UI)
    may lag by up to ``_FLUSH_INTERVAL_S`` — the accepted, intended behaviour.

    A5: this only ever WRITES; the buffer is never read for an auth decision.
    """
    now = _now_monotonic()
    with _lock:
        _last_used_buffer[token_id] = iso_z_now()
        last = _last_flush_at.get(token_id)
        if last is not None and now - last < _FLUSH_INTERVAL_S:
            return  # inside this token's throttle window — keep buffered, no write
        pending = tuple(_last_used_buffer)  # ids attempted by this flush
        try:
            _flush_last_used_locked()
        except Exception:
            # A cosmetic last-used timestamp must NEVER fail an authorized
            # request. On a write error (e.g. Windows os.replace PermissionError
            # while an AV scanner holds auth.json, or disk full) degrade to
            # "not updated": the pending timestamps are dropped (the flush
            # already drained the buffer, keeping it bounded) and re-recorded on
            # the next accepted request. Log the token id ONLY — never the
            # secret or the full credential.
            log.warning("could not persist last_used_at for token %s", token_id)
        # Advance the throttle for every attempted id (success or degrade) so a
        # failing writer is not hammered once per accepted request.
        for tid in pending:
            _last_flush_at[tid] = now
