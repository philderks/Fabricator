"""C1: CORS should be locked down by default."""
from __future__ import annotations

import pytest


def test_default_host_is_loopback(monkeypatch):
    monkeypatch.delenv("HOST", raising=False)
    monkeypatch.delenv("FLASK_ENV", raising=False)
    from backend.core.config import get_config
    assert get_config().HOST == "127.0.0.1"


def test_wildcard_cors_default_is_rejected(monkeypatch):
    """A fresh install must not default CORS_ORIGINS to '*'."""
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    from backend.core.config import get_config
    default = get_config().CORS_ORIGINS
    # Must be a concrete list of one or more origins, never '*'.
    assert default != "*"
    assert isinstance(default, (list, tuple))
    assert all(o.startswith(("http://", "https://")) for o in default)


def test_cors_origins_env_parses_csv(monkeypatch):
    monkeypatch.setenv(
        "CORS_ORIGINS",
        "http://localhost:3000, https://ui.example.com",
    )
    from backend.core.config import get_config
    origins = get_config().CORS_ORIGINS
    assert origins == ["http://localhost:3000", "https://ui.example.com"]


def test_explicit_wildcard_origin_raises(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "*")
    from backend.core.config import get_config
    with pytest.raises(ValueError, match="(?i)wildcard"):
        get_config()


def test_malformed_origin_raises(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "not-a-url")
    from backend.core.config import get_config
    with pytest.raises(ValueError, match="http"):
        get_config()


def test_env_changes_reflected_between_calls(monkeypatch):
    """Config reads env at construction — second call sees the new value."""
    from backend.core.config import get_config
    monkeypatch.setenv("CORS_ORIGINS", "http://a.test")
    assert get_config().CORS_ORIGINS == ["http://a.test"]
    monkeypatch.setenv("CORS_ORIGINS", "http://b.test")
    assert get_config().CORS_ORIGINS == ["http://b.test"]


def test_cors_header_rejects_unlisted_origin(client):
    """Conftest sets CORS_ORIGINS to http://localhost:3000 only."""
    resp = client.get(
        "/api/health",
        headers={"Origin": "http://evil.example.com"},
    )
    assert resp.status_code == 200
    # Flask-CORS omits ACAO header for disallowed origins.
    assert resp.headers.get("Access-Control-Allow-Origin") in (None, "")


def test_cors_header_allows_listed_origin(client):
    resp = client.get(
        "/api/health",
        headers={"Origin": "http://localhost:3000"},
    )
    assert resp.status_code == 200
    assert resp.headers.get("Access-Control-Allow-Origin") == "http://localhost:3000"
