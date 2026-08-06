"""Root replacement must fire only where a path can actually start and end.

The live run's second finding. ``_known_roots`` includes the data directory,
which on the Docker image -- the deployment most self-hosters run -- is
``/data``. Every Modrinth CDN URL contains ``/data/``, and the old code did a
plain ``str.replace`` of each root with no anchoring, so those URLs came back
as ``https://cdn.modrinth.com<path>/AANobbMI/...``.

It was invisible because every existing test ran against the Windows dev tree,
where the roots are long temp paths that appear in no URL. So the root shape is
PARAMETERISED here: the same assertions run against POSIX/Docker roots and
against Windows roots, and the Docker case is the one that used to fail.

Assertions are on parsed values, never on raw response text.
"""
from __future__ import annotations

import pytest

# Real values.
MODRINTH_JAR_URL = (
    "https://cdn.modrinth.com/data/AANobbMI/versions/OihdIimA/"
    "sodium-fabric-0.5.13%2Bmc1.20.1.jar"
)
MODRINTH_ICON_URL = (
    "https://cdn.modrinth.com/data/AANobbMI/"
    "295862f4724dc3f78df3447ad6072b2dcd3ef0c9_96.webp"
)

# As the Docker image sets them: SERVER_ROOT=/data/servers, JAVA_ROOT=/data/java,
# BACKUPS_DIR=/data/backups, SERVER_INDEX_FILE=/data/servers.json -> parent /data.
DOCKER_ROOTS = ["/data/backups", "/data/servers", "/data/java", "/data", "/tmp"]
DOCKER_ROOTS = sorted(DOCKER_ROOTS, key=len, reverse=True)

WINDOWS_ROOTS = sorted(
    [
        r"C:\Users\Linus\AppData\Local\Temp\fab\data\servers",
        r"C:\Users\Linus\AppData\Local\Temp\fab\data",
    ],
    key=len,
    reverse=True,
)

ROOT_SHAPES = [pytest.param(DOCKER_ROOTS, id="docker"), pytest.param(WINDOWS_ROOTS, id="windows")]


@pytest.mark.parametrize("roots", ROOT_SHAPES)
@pytest.mark.parametrize("url", [MODRINTH_JAR_URL, MODRINTH_ICON_URL])
def test_a_modrinth_url_survives_whatever_the_roots_look_like(roots, url):
    """The docker case is the regression: /data lives inside every CDN URL."""
    from backend.auth.redaction import _scrub_text

    assert _scrub_text(url, roots) == url


def test_a_real_docker_server_path_is_still_scrubbed():
    from backend.auth.redaction import _scrub_text

    scrubbed = _scrub_text(
        "could not write /data/servers/srv_1/mods/sodium.jar", DOCKER_ROOTS
    )
    assert "/data/servers" not in scrubbed
    assert "<path>" in scrubbed
    assert "sodium.jar" in scrubbed  # the tail a diagnosis needs survives


def test_a_real_windows_path_is_still_scrubbed():
    from backend.auth.redaction import _scrub_text

    path = r"C:\Users\Linus\AppData\Local\Temp\fab\data\servers\srv_1\mods\sodium.jar"
    scrubbed = _scrub_text(f"could not write {path}", WINDOWS_ROOTS)
    assert r"C:\Users" not in scrubbed
    assert "<path>" in scrubbed
    assert "sodium.jar" in scrubbed


def test_the_bare_data_root_is_scrubbed_at_end_of_string():
    from backend.auth.redaction import _scrub_text

    assert _scrub_text("wrote to /data", DOCKER_ROOTS) == "wrote to <path>"


def test_a_root_is_not_matched_inside_a_longer_directory_name():
    """/data must not eat the first five characters of /database."""
    from backend.auth.redaction import _scrub_text

    assert _scrub_text("/database/dump.sql", DOCKER_ROOTS) == "/database/dump.sql"


def test_a_url_and_a_docker_path_in_one_string_are_treated_differently():
    from backend.auth.redaction import _scrub_text

    text = f"downloaded {MODRINTH_JAR_URL} to /data/servers/srv_1/mods/sodium.jar"
    scrubbed = _scrub_text(text, DOCKER_ROOTS)
    assert MODRINTH_JAR_URL in scrubbed
    assert "/data/servers" not in scrubbed


# --- the pathological root ---------------------------------------------------

@pytest.mark.parametrize("root", ["/", "\\", "C:\\", "C:/", "", "   ", "/a", "/ab"])
def test_roots_too_generic_to_match_are_rejected(root):
    """A filesystem root names no directory and would match inside everything."""
    from backend.auth.redaction import _is_usable_root, _normalise_root

    assert not _is_usable_root(_normalise_root(root))


@pytest.mark.parametrize("root", ["/tmp", "/data", "/data/servers", r"C:\Users\Linus", "/var/lib/fabricator"])
def test_real_roots_are_accepted(root):
    from backend.auth.redaction import _is_usable_root, _normalise_root

    assert _is_usable_root(_normalise_root(root))


def test_a_trailing_separator_does_not_change_a_root():
    from backend.auth.redaction import _normalise_root

    assert _normalise_root("/data/") == "/data"
    assert _normalise_root("C:\\Users\\Linus\\") == r"C:\Users\Linus"


def test_a_slash_root_leaves_text_untouched_rather_than_destroying_it():
    """Stated consequence: with "/" as a root, nothing is replaced by that root."""
    from backend.auth.redaction import _scrub_text

    text = "could not write /srv/x.jar while fetching https://example.com/a/b"
    assert _scrub_text(text, ["/"]) == text


# --- through the real hook, with the config a Docker install actually has ----

def _docker_token_response(auth_app, payload):
    from flask import g, jsonify
    from backend.auth.redaction import TOKEN_REQUEST_FLAG, redact_token_response

    with auth_app.test_request_context("/api/modrinth/mod/x/download-url"):
        auth_app.config.update(
            SERVERS_ROOT="/data/servers",
            JAVA_ROOT="/data/java",
            BACKUPS_DIR="/data/backups",
            SERVERS_FILE="/data/servers.json",
        )
        setattr(g, TOKEN_REQUEST_FLAG, True)
        return redact_token_response(jsonify(payload)).get_json()


def test_known_roots_uses_the_docker_data_dir_but_not_a_bare_slash(auth_app):
    from pathlib import Path

    from backend.auth.redaction import _known_roots, _normalise_root

    with auth_app.test_request_context("/api/health"):
        auth_app.config.update(
            SERVERS_ROOT="/data/servers", JAVA_ROOT="/data/java",
            BACKUPS_DIR="/data/backups", SERVERS_FILE="/data/servers.json",
        )
        roots = _known_roots()

    # The data dir IS used. It is derived through pathlib, so its separator is
    # whatever the host platform renders — "/data" on the Linux image this case
    # models, "\\data" when these tests run on Windows. Compare the same way the
    # code derives it rather than hard-coding one platform's spelling.
    data_dir = _normalise_root(Path("/data/servers.json").parent)
    assert data_dir in roots
    assert "/data/servers" in roots   # taken verbatim from config, not via Path
    assert "/" not in roots           # a bare filesystem root never is
    assert roots == sorted(roots, key=len, reverse=True)


def test_the_hook_leaves_a_download_url_usable_on_a_docker_install(auth_app):
    body = _docker_token_response(auth_app, {"download_url": MODRINTH_JAR_URL})
    assert body["download_url"] == MODRINTH_JAR_URL


def test_the_hook_still_scrubs_a_docker_path_in_an_error(auth_app):
    body = _docker_token_response(
        auth_app, {"error": "could not write /data/servers/srv_1/mods/x.jar"}
    )
    assert "/data/servers" not in body["error"]
    assert "<path>" in body["error"]


def test_a_session_response_is_untouched_on_a_docker_install(auth_app):
    from flask import jsonify
    from backend.auth.redaction import redact_token_response

    payload = {
        "download_url": MODRINTH_JAR_URL,
        "installPath": "/data/servers/srv_1",
    }
    with auth_app.test_request_context("/api/servers"):
        auth_app.config.update(SERVERS_FILE="/data/servers.json")
        body = redact_token_response(jsonify(payload)).get_json()

    assert body == payload
