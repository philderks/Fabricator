"""Unit tests for backend.auth.service (pure, Flask-free)."""
from __future__ import annotations

import pytest

from backend.auth import service


def test_hash_password_is_verifiable(monkeypatch):
    h = service.hash_password("correct horse battery staple")
    monkeypatch.setenv("FABRICATOR_AUTH_PASSWORD_HASH", h)
    assert service.verify_password("correct horse battery staple") is True
    assert service.verify_password("wrong") is False


def test_verify_password_false_when_unset(monkeypatch):
    monkeypatch.delenv("FABRICATOR_AUTH_PASSWORD_HASH", raising=False)
    assert service.verify_password("anything") is False


def test_get_password_hash_none_when_empty(monkeypatch):
    monkeypatch.setenv("FABRICATOR_AUTH_PASSWORD_HASH", "")
    assert service.get_password_hash() is None


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on", " 1 "])
def test_auth_disabled_truthy(monkeypatch, value):
    monkeypatch.setenv("FABRICATOR_DISABLE_AUTH", value)
    assert service.auth_disabled() is True


@pytest.mark.parametrize("value", ["0", "false", "no", "off", "", "nope"])
def test_auth_disabled_failsafe(monkeypatch, value):
    # SECURITY: anything that is not an explicit truthy keeps auth ENABLED.
    monkeypatch.setenv("FABRICATOR_DISABLE_AUTH", value)
    assert service.auth_disabled() is False


def test_auth_disabled_unset(monkeypatch):
    monkeypatch.delenv("FABRICATOR_DISABLE_AUTH", raising=False)
    assert service.auth_disabled() is False


def test_verify_password_false_on_malformed_hash(monkeypatch):
    monkeypatch.setenv("FABRICATOR_AUTH_PASSWORD_HASH", "not-a-valid-hash")
    assert service.verify_password("anything") is False


@pytest.mark.parametrize(
    "value,expected",
    [
        ("1", True),
        ("true", True),
        ("yes", True),
        ("on", True),
        ("0", False),
        ("", False),
        ("nope", False),
    ],
)
def test_cookie_secure_parsing(monkeypatch, value, expected):
    monkeypatch.setenv("FABRICATOR_SESSION_COOKIE_SECURE", value)
    assert service.cookie_secure() is expected
