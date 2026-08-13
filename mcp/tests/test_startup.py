"""Startup refuses to run half-configured, and never echoes the token."""
from __future__ import annotations

import httpx
import pytest

from fabricator_mcp.__main__ import EXIT_CONFIG_ERROR, main
from fabricator_mcp.config import DEFAULT_URL, ConfigError, PanelConfig

_TOKEN = "fab_abc123_supersecretvalue"


def test_missing_token_exits_with_an_actionable_message(env, capsys):
    env.setenv("FABRICATOR_URL", "http://127.0.0.1:5000")

    assert main([]) == EXIT_CONFIG_ERROR

    err = capsys.readouterr().err
    assert "FABRICATOR_TOKEN" in err
    assert "Settings" in err


@pytest.mark.parametrize("value", ["", "   "])
def test_blank_token_is_treated_as_missing(env, value, capsys):
    env.setenv("FABRICATOR_TOKEN", value)

    assert main([]) == EXIT_CONFIG_ERROR
    assert "FABRICATOR_TOKEN" in capsys.readouterr().err


@pytest.mark.parametrize(
    "url", ["ftp://panel.local", "not-a-url", "://missing-scheme", "http://"]
)
def test_unusable_url_exits(env, url, capsys):
    env.setenv("FABRICATOR_TOKEN", _TOKEN)
    env.setenv("FABRICATOR_URL", url)

    assert main([]) == EXIT_CONFIG_ERROR
    assert "FABRICATOR_URL" in capsys.readouterr().err


def test_startup_failure_never_prints_the_token(env, capsys):
    env.setenv("FABRICATOR_TOKEN", _TOKEN)
    env.setenv("FABRICATOR_URL", "ftp://nope")

    main([])

    captured = capsys.readouterr()
    assert _TOKEN not in captured.err
    assert _TOKEN not in captured.out


def test_url_defaults_and_trailing_slash_is_dropped(env):
    env.setenv("FABRICATOR_TOKEN", _TOKEN)
    assert PanelConfig.from_env().url == DEFAULT_URL

    env.setenv("FABRICATOR_URL", "https://mc.example.lan:8443/")
    assert PanelConfig.from_env().url == "https://mc.example.lan:8443"


def test_repr_does_not_leak_the_token(env):
    env.setenv("FABRICATOR_TOKEN", _TOKEN)
    rendered = repr(PanelConfig.from_env())
    assert _TOKEN not in rendered
    assert "redacted" in rendered


def test_config_error_is_raised_not_swallowed(env):
    with pytest.raises(ConfigError):
        PanelConfig.from_env({})


def test_the_no_network_guard_actually_blocks(env):
    """The guard is the reason 'no live network' is a fact and not a wish."""
    with pytest.raises(AssertionError, match="un-mocked network call"):
        httpx.Client().get("http://127.0.0.1:5000/api/health")
