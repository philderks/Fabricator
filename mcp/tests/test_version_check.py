"""The startup skew warning: one line, or silence, and never a refusal."""
from __future__ import annotations

import io

import httpx
import pytest

from fabricator_mcp.config import PanelConfig
from fabricator_mcp.version_check import (
    MINIMUM_PANEL_VERSION,
    parse_version,
    warn_if_panel_is_old,
    warning_for,
)

_CONFIG = PanelConfig(url="http://panel.test:5000", token="fab_id_secret")


# --- parsing -----------------------------------------------------------------

@pytest.mark.parametrize(
    "value,expected",
    [
        ("1.1.0", (1, 1, 0)),
        ("v1.0.3", (1, 0, 3)),          # the panel's own tag shape
        ("V2.0.0", (2, 0, 0)),
        ("1.1.0-rc1", (1, 1, 0)),       # pre-release suffix dropped
        ("1.2.0+build7", (1, 2, 0)),
        ("  1.0.3  ", (1, 0, 3)),
        ("1.2", (1, 2)),
        ("1.2.x", (1, 2)),              # keeps the numeric prefix it understood
    ],
)
def test_versions_that_parse(value, expected):
    assert parse_version(value) == expected


@pytest.mark.parametrize(
    "value", ["unknown", "", "   ", None, 17, "abc", "dev", "a1b2c3d", "v", "-1.2"]
)
def test_values_that_are_not_versions_parse_to_none(value):
    """None means 'no version reported' — never version zero."""
    assert parse_version(value) is None


# --- the decision ------------------------------------------------------------

@pytest.mark.parametrize("older", ["1.0.3", "v1.0.3", "0.9.0", "1.0"])
def test_a_panel_below_the_marker_warns(older):
    message = warning_for(older, minimum="1.1.0")
    assert message is not None


@pytest.mark.parametrize("current", ["1.1.0", "v1.1.0", "1.1", "1.2.0", "2.0.0", "1.1.0-rc1"])
def test_a_panel_at_or_above_the_marker_is_silent(current):
    """1.1 and 1.1.0 are the same version, not an older one."""
    assert warning_for(current, minimum="1.1.0") is None


@pytest.mark.parametrize("value", ["unknown", "", None, "abc"])
def test_a_panel_that_reports_no_usable_version_is_silent(value):
    """Nothing was checked, so nothing is claimed."""
    assert warning_for(value, minimum="1.1.0") is None


def test_the_warning_names_both_versions_so_the_user_can_act():
    message = warning_for("1.0.3", minimum="1.1.0")
    assert "1.0.3" in message      # what they have
    assert "1.1.0" in message      # what is needed
    assert "Starting anyway" in message


def test_the_marker_itself_parses():
    """A marker that did not parse would silently disable the whole check."""
    assert parse_version(MINIMUM_PANEL_VERSION) is not None


# --- the startup probe -------------------------------------------------------

def _status_transport(body, status_code=200):
    def handler(_request):
        return httpx.Response(status_code, json=body)

    return httpx.MockTransport(handler)


def _run(body, status_code=200):
    stream = io.StringIO()
    transport = _status_transport(body, status_code)
    message = warn_if_panel_is_old(_CONFIG, transport=transport, stream=stream)
    return message, stream.getvalue()


def test_an_old_panel_warns_exactly_once():
    message, written = _run({"panel_version": "1.0.3"})

    assert message is not None
    assert written.count("fabricator-mcp:") == 1
    assert written.strip().count("\n") == 0     # one line, not a paragraph per call
    assert "1.0.3" in written and MINIMUM_PANEL_VERSION in written


def test_a_current_panel_writes_nothing():
    message, written = _run({"panel_version": "9.9.9"})
    assert message is None
    assert written == ""


def test_a_panel_without_the_field_writes_nothing():
    """Older panels predate panel_version; that is not a version mismatch."""
    message, written = _run({"enabled": True, "authenticated": True})
    assert message is None
    assert written == ""


def test_a_source_build_reporting_unknown_writes_nothing():
    message, written = _run({"panel_version": "unknown"})
    assert message is None
    assert written == ""


def test_an_unparseable_version_is_treated_as_unknown():
    message, written = _run({"panel_version": "nightly-abc123"})
    assert message is None
    assert written == ""


def test_an_unreachable_panel_does_not_warn_and_does_not_raise():
    """A probe that could not run says nothing about the panel's version."""
    def handler(request):
        raise httpx.ConnectError("connection refused", request=request)

    stream = io.StringIO()
    message = warn_if_panel_is_old(
        _CONFIG, transport=httpx.MockTransport(handler), stream=stream
    )
    assert message is None
    assert stream.getvalue() == ""


def test_a_rejected_token_does_not_warn_and_does_not_raise():
    message, written = _run({"error": "invalid token"}, status_code=401)
    assert message is None
    assert written == ""


def test_a_broken_panel_response_does_not_stop_startup():
    def handler(_request):
        return httpx.Response(200, content=b"not json at all")

    stream = io.StringIO()
    assert warn_if_panel_is_old(
        _CONFIG, transport=httpx.MockTransport(handler), stream=stream
    ) is None
    assert stream.getvalue() == ""
