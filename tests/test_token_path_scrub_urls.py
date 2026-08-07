"""The path scrub must not touch URLs.

Regression for a defect a live run found and 1024 green tests did not: the
drive-letter pattern also matched the "s:/" inside "https://", so every URL a
token caller received came back as "http<path>". That broke the diagnosis loop
at the point where it concludes — check_mod_compatibility and get_mod_info hand
the agent a download link.

The values below are real ones taken off the wire during that run, not
illustrative ones, because the illustrative values are exactly what missed it.

Assertions are on PARSED values, never on raw response text: a Windows path is
trivially absent from raw JSON because the backslashes are escaped, and that
mistake has already been made once in this unit.
"""
from __future__ import annotations

import pytest

# Real values observed on the wire.
MODRINTH_JAR_URL = (
    "https://cdn.modrinth.com/data/AANobbMI/versions/OihdIimA/"
    "sodium-fabric-0.5.13%2Bmc1.20.1.jar"
)
MODRINTH_ICON_URL = "https://cdn.modrinth.com/data/AANobbMI/icon.png?size=64&v=2"
PANEL_URL = "http://127.0.0.1:5000/api/servers"
WINDOWS_PATH = r"C:\Users\Linus\AppData\Local\servers\srv_1\mods\sodium.jar"
POSIX_ROOT = "/data/servers"
POSIX_PATH = "/data/servers/srv_1/mods/sodium.jar"


@pytest.mark.parametrize(
    "url",
    [
        MODRINTH_JAR_URL,          # note the %2B — Modrinth filenames carry one
        MODRINTH_ICON_URL,         # query string
        PANEL_URL,                 # the panel's own URL
        "see the docs at https://example.com/help",
        "http://localhost:5000/api/health",
    ],
)
def test_urls_survive_the_scrub_untouched(url):
    from backend.auth.redaction import _scrub_text

    assert _scrub_text(url, []) == url


def test_a_windows_path_is_still_scrubbed():
    from backend.auth.redaction import _scrub_text

    scrubbed = _scrub_text(WINDOWS_PATH, [])
    assert "C:\\Users" not in scrubbed
    assert "<path>" in scrubbed


def test_a_windows_path_inside_an_error_sentence_is_still_scrubbed():
    from backend.auth.redaction import _scrub_text

    text = f"could not write {WINDOWS_PATH} (access denied)"
    scrubbed = _scrub_text(text, [])
    assert "C:\\Users" not in scrubbed
    assert scrubbed.startswith("could not write ")
    assert scrubbed.endswith(" (access denied)")


def test_a_forward_slash_drive_path_is_still_scrubbed():
    from backend.auth.redaction import _scrub_text

    assert _scrub_text("C:/Users/Linus/servers/x.jar", []) == "<path>"


def test_a_posix_path_under_a_known_root_is_still_scrubbed():
    from backend.auth.redaction import _scrub_text

    scrubbed = _scrub_text(f"could not write {POSIX_PATH}", [POSIX_ROOT])
    assert POSIX_ROOT not in scrubbed
    assert "<path>" in scrubbed
    # The tail a diagnosis needs survives.
    assert "sodium.jar" in scrubbed


def test_a_url_and_a_path_in_one_string_are_treated_differently():
    from backend.auth.redaction import _scrub_text

    text = f"downloaded {MODRINTH_JAR_URL} to {WINDOWS_PATH}"
    scrubbed = _scrub_text(text, [])
    assert MODRINTH_JAR_URL in scrubbed
    assert "C:\\Users" not in scrubbed


# --- through the actual response hook, on the actual token path -------------

def _token_response(auth_app, payload):
    """Run the real after_request hook over `payload` as a token request."""
    from flask import g, jsonify
    from backend.auth.redaction import TOKEN_REQUEST_FLAG, redact_token_response

    with auth_app.test_request_context("/api/modrinth/mod/x/download-url"):
        setattr(g, TOKEN_REQUEST_FLAG, True)
        response = redact_token_response(jsonify(payload))
        return response.get_json()


def test_the_hook_leaves_a_download_url_usable(auth_app):
    body = _token_response(auth_app, {"download_url": MODRINTH_JAR_URL})
    assert body["download_url"] == MODRINTH_JAR_URL


def test_the_hook_leaves_a_nested_icon_url_usable(auth_app):
    body = _token_response(
        auth_app, {"resolved": {"sodium.jar": {"iconUrl": MODRINTH_ICON_URL}}}
    )
    assert body["resolved"]["sodium.jar"]["iconUrl"] == MODRINTH_ICON_URL


def test_the_hook_still_scrubs_a_windows_path_in_an_error(auth_app):
    body = _token_response(auth_app, {"error": f"could not write {WINDOWS_PATH}"})
    assert "C:\\Users" not in body["error"]
    assert "<path>" in body["error"]


def test_a_session_response_is_untouched(auth_app):
    """No token flag: the operator's own traffic keeps both values verbatim."""
    from flask import jsonify
    from backend.auth.redaction import redact_token_response

    payload = {"download_url": MODRINTH_JAR_URL, "installPath": WINDOWS_PATH}
    with auth_app.test_request_context("/api/servers"):
        body = redact_token_response(jsonify(payload)).get_json()

    assert body == payload
