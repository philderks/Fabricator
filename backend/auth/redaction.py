"""Credential and host-path redaction for MCP token responses.

THE RULE: a token caller never receives a credential and never receives a host
filesystem path. One sentence, checkable, no per-route judgement.

This is ONE filter on ONE hook, not a projection per route. It is registered as
an ``after_request`` in :func:`backend.auth.init_auth`, right next to the single
gate clause that authorises the token in the first place, so it sees the body of
EVERY response on the token path -- every route that exists today and every
route added later, with no second edit. Twelve routes leak today; twelve
per-route projections would be twelve chances to miss one, and the thirteenth
route would be uncovered again the day it lands.

HONEST WEAKNESS: this filter is KEY-based, so it is a deny-list. A future field
with a credential in it under a name this list does not know slips straight
through. That is covered -- deliberately from the other side -- by
``tests/test_token_response_canaries.py`` being VALUE-based: it plants canary
values and goes RED wherever one surfaces, whatever the key is called. The two
layers together still leave one real gap: a genuinely new credential field that
no fixture plants is undetected by both. That residual is not defined away, and
closing it for a given field means planting that field in the canary fixture.

Session requests are untouched. The hook returns the response object unmodified
unless the gate marked this request token-authenticated, so operator traffic
stays byte-identical.
"""
from __future__ import annotations

import re
import tempfile
from functools import lru_cache
from pathlib import Path

from flask import current_app, g, json

#: Set on ``flask.g`` by the gate when a bearer token has been authorised.
TOKEN_REQUEST_FLAG = "mcp_token_request"

# Substring markers. ``rconPassword`` is caught by "password".
#
# "hash" is deliberately NOT a marker: Modrinth file hashes (``hashes``) are
# public catalog data a mod-diagnosis client legitimately needs, and the only
# hash that would matter here -- ``password_hash`` -- already matches
# "password".
_CREDENTIAL_MARKERS = (
    "password",
    "passwd",
    "secret",
    "token",
    "pepper",
    "credential",
)

# Exact keys that are credentials on their own but too short to match as a
# substring without catching innocent words ("monkey", "keys").
_CREDENTIAL_KEYS = frozenset({"key", "apikey", "api_key"})


def is_token_request() -> bool:
    """True when the gate authorised this request via an MCP bearer token.

    Lives here (a leaf module importing only Flask) so route modules can ask the
    question without importing the auth package and creating a cycle.
    """
    return bool(g.get(TOKEN_REQUEST_FLAG))


def _is_credential_key(key: str) -> bool:
    lowered = key.lower()
    if lowered in _CREDENTIAL_KEYS:
        return True
    return any(marker in lowered for marker in _CREDENTIAL_MARKERS)


def _is_path_key(key: str) -> bool:
    """Any key naming a filesystem location.

    Matching on the "path" suffix covers ``path``, ``filePath``, ``installPath``,
    ``javaPath``, ``storagePath``, ``defaultStoragePath``, ``java_path`` and the
    plural ``deleted_paths`` without an enumeration that a new route could fall
    outside of. ``relativePath`` is caught too: it discloses no host layout, but
    the rule stays "no per-key judgement", and the bare filename in ``name``
    remains as the handle a caller needs.
    """
    lowered = key.lower()
    return lowered.endswith("path") or lowered.endswith("paths")


def is_redacted_key(key: str) -> bool:
    return _is_credential_key(key) or _is_path_key(key)


def redact(value):
    """Recursively drop redacted keys at every nesting depth.

    Applies to embedded objects inside a success envelope AND inside an error
    shape -- a 400/409 that carries the server record leaks exactly the same
    fields as the 200 does.
    """
    if isinstance(value, dict):
        return {
            key: redact(item)
            for key, item in value.items()
            if not is_redacted_key(key)
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


# --------------------------------------------------------------------------- #
# Host paths inside string VALUES.
#
# This is a SECOND, separate mechanism, and the key filter above does not cover
# it: ``redact`` drops fields by name and never looks inside a string. The
# progress/task stores (install progress, java install tasks, backup jobs,
# modpack install progress) carry Python exception text, and an exception that
# failed on a file quotes that file's absolute path inside an ``error`` string.
# Server logs are the same shape -- a stack trace names the paths it touched.
#
# Strategy: replace the panel's own root PREFIXES and leave the remainder. Host
# layout (drive, user, data dir) is what must not leave; the relative tail is
# what a crash diagnosis actually needs, so
# ``C:\Users\x\servers\srv_1\mods\sodium.jar`` becomes
# ``<path>\srv_1\mods\sodium.jar`` and the mod name survives. An absolute path
# that is NOT under one of our roots is not ours to interpret, so it is replaced
# whole.
#
# RESIDUAL: this catches the panel's own roots plus Windows drive-letter paths.
# A POSIX absolute path outside every known root that gets embedded in an
# exception string (a foreign library quoting /etc/something) is NOT scrubbed --
# a blanket POSIX path regex would mangle URLs and API paths, which is a worse
# trade. Named here rather than defined away.
# --------------------------------------------------------------------------- #

_PLACEHOLDER = "<path>"

# A drive-letter absolute path, and ONLY that.
#
# The obvious pattern -- [A-Za-z]:[\\/] -- also matches the "s:/" inside
# "https://" and the "p:/" inside "http://", which silently destroyed every URL
# a token caller received: a Modrinth download link came back as "http<path>".
# A live run found that; no unit test did, because the fixtures on one side used
# path values and the mocks on the other side never carried a real URL.
#
# The guard is a boundary, not a scheme blacklist: a drive letter is a SINGLE
# letter, so anything alphanumeric immediately before it means this is the tail
# of a longer word (the "s" of "https") and not a drive. That keeps the rule one
# line and needs no list of schemes to stay current.
#
# What this deliberately does NOT catch:
#   * a drive path glued to the preceding word with no separator
#     ("openC:\x") -- real messages put a space, quote, or line start first;
#   * UNC paths (\\server\share\...), which the old pattern did not catch either;
#   * POSIX absolute paths outside the known roots (the pre-existing residual
#     noted above).
_WINDOWS_ABS_PATH = re.compile(r"(?<![A-Za-z0-9])[A-Za-z]:[\\/][^\s\"'<>|]*")

_ROOT_CONFIG_KEYS = ("SERVERS_ROOT", "JAVA_ROOT", "BACKUPS_DIR")

# A root shorter than this is too generic to look for inside arbitrary text.
# "/tmp" is the shortest real one we use, so the floor sits just under it.
_MIN_ROOT_LENGTH = 4


def _normalise_root(value) -> str:
    """Trim a root to a comparable form: no trailing separator."""
    text = str(value).strip()
    while len(text) > 1 and text[-1] in "\\/":
        text = text[:-1]
    return text


def _is_usable_root(root: str) -> bool:
    """True when a root is specific enough to be matched inside text at all.

    A filesystem root -- "/", "C:\\" -- names no directory of its own and would
    match inside every absolute path and most URLs, so it is dropped rather than
    used. The consequence is stated rather than hidden: if the data directory
    really is "/", paths under it are not scrubbed by this pass. There is no
    version of substring replacement on "/" that is not worse.
    """
    if len(root) < _MIN_ROOT_LENGTH:
        return False
    return bool(Path(root).name)


@lru_cache(maxsize=64)
def _root_pattern(root: str) -> "re.Pattern[str]":
    """Match ``root`` only where a filesystem path could actually begin and end.

    Two boundaries, and both are load-bearing:

    * BEFORE -- not preceded by an alphanumeric. This is what keeps "/data" from
      matching inside "https://cdn.modrinth.com/data/AANobbMI/...", where it is
      preceded by the "m" of ".com". On the Docker image the data directory IS
      "/data", so without this every Modrinth URL a token caller received was
      corrupted. Same shape of guard as the drive-letter pattern above, for the
      same reason.
    * AFTER -- a separator, whitespace, a quote, or end of string. This is what
      keeps the root "/data" from matching the first five characters of
      "/database/x.jar", which is a different directory entirely.
    """
    return re.compile(
        r"(?<![A-Za-z0-9])" + re.escape(root) + r"(?=[\\/]|[\s\"'<>|]|$)"
    )


def _known_roots():
    """The panel's own filesystem roots, longest first so nesting resolves."""
    config = current_app.config
    roots = set()
    for key in _ROOT_CONFIG_KEYS:
        value = config.get(key)
        if value:
            roots.add(_normalise_root(value))
    servers_file = config.get("SERVERS_FILE")
    if servers_file:
        # data dir (auth.json lives here); on the Docker image this is "/data"
        roots.add(_normalise_root(Path(servers_file).parent))
    roots.add(_normalise_root(tempfile.gettempdir()))  # loader metadata staging
    usable = (root for root in roots if root and _is_usable_root(root))
    return sorted(usable, key=len, reverse=True)


def _scrub_text(text: str, roots) -> str:
    for root in roots:
        # The usability guard lives HERE, not only in _known_roots, so that a
        # root too generic to match safely is refused wherever it comes from.
        if not root or not _is_usable_root(root):
            continue
        if root in text:  # cheap pre-check before the anchored match
            text = _root_pattern(root).sub(_PLACEHOLDER, text)
    return _WINDOWS_ABS_PATH.sub(_PLACEHOLDER, text)


def scrub_paths(value, roots):
    """Recursively replace host paths inside string values."""
    if isinstance(value, dict):
        return {key: scrub_paths(item, roots) for key, item in value.items()}
    if isinstance(value, list):
        return [scrub_paths(item, roots) for item in value]
    if isinstance(value, str):
        return _scrub_text(value, roots)
    return value


def redact_token_response(response):
    """``after_request`` hook for the token path.

    Two independent passes: the key filter (credentials and path-named fields)
    and, separately, the string scrub for host paths embedded in error text.
    """
    if not g.get(TOKEN_REQUEST_FLAG):
        return response  # session (or non-token) request: untouched, byte-identical
    if not response.is_json:
        return response
    payload = response.get_json(silent=True)
    if payload is None:
        return response
    cleaned = scrub_paths(redact(payload), _known_roots())
    if cleaned != payload:
        response.set_data(json.dumps(cleaned))
    return response
