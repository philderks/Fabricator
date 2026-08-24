"""Release selection for the Fabricator CLI updater."""
from unittest.mock import MagicMock

import tools.cli as cli


def _response(releases):
    response = MagicMock()
    response.json.return_value = releases
    return response


def test_latest_release_tag_uses_first_eligible_release_in_api_order(monkeypatch):
    releases = [
        {"tag_name": "v2.0.0"},
        {"tag_name": "v1.9.0"},
    ]
    monkeypatch.setattr(cli.requests, "get", lambda *args, **kwargs: _response(releases))

    assert cli._get_latest_release_tag() == "v2.0.0"


def test_latest_release_tag_skips_leading_mcp_release(monkeypatch):
    releases = [
        {"tag_name": "mcp-v0.1.0"},
        {"tag_name": "v2.0.0"},
    ]
    monkeypatch.setattr(cli.requests, "get", lambda *args, **kwargs: _response(releases))

    assert cli._get_latest_release_tag() == "v2.0.0"


def test_latest_release_tag_returns_none_when_no_eligible_release_exists(monkeypatch):
    releases = [
        {"tag_name": "mcp-v0.1.0"},
        {"tag_name": "other-v1.0.0"},
    ]
    monkeypatch.setattr(cli.requests, "get", lambda *args, **kwargs: _response(releases))

    assert cli._get_latest_release_tag() is None
