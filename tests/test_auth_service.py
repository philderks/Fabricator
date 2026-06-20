"""Unit tests for backend.auth.service."""
from __future__ import annotations

import json
import stat

import pytest

from backend.auth import service


# --------------------------------------------------------------------------- #
# Hashing / verification
# --------------------------------------------------------------------------- #

def test_hash_password_is_verifiable(monkeypatch):
    h = service.hash_password("correct horse battery staple")
    monkeypatch.setenv("FABRICATOR_AUTH_PASSWORD_HASH", h)
    assert service.verify_password("correct horse battery staple") is True
    assert service.verify_password("wrong") is False


def test_verify_password_false_when_unset(tmp_servers_root, monkeypatch):
    monkeypatch.delenv("FABRICATOR_AUTH_PASSWORD_HASH", raising=False)
    assert service.verify_password("anything") is False


def test_verify_password_false_on_malformed_hash(monkeypatch):
    monkeypatch.setenv("FABRICATOR_AUTH_PASSWORD_HASH", "not-a-valid-hash")
    assert service.verify_password("anything") is False


def test_get_password_hash_none_when_empty(tmp_servers_root, monkeypatch):
    monkeypatch.setenv("FABRICATOR_AUTH_PASSWORD_HASH", "")
    assert service.get_password_hash() is None


# --------------------------------------------------------------------------- #
# Flag parsing (fail-safe)
# --------------------------------------------------------------------------- #

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


# --------------------------------------------------------------------------- #
# Credential persistence (env > file > None) + the one-time setup guard
# --------------------------------------------------------------------------- #

def test_get_password_hash_env_overrides_file(tmp_servers_root, monkeypatch):
    monkeypatch.delenv("FABRICATOR_AUTH_PASSWORD_HASH", raising=False)
    service.set_password("from-file")
    monkeypatch.setenv(
        "FABRICATOR_AUTH_PASSWORD_HASH", service.hash_password("from-env")
    )
    assert service.verify_password("from-env") is True
    assert service.verify_password("from-file") is False  # env wins


def test_get_password_hash_reads_file_when_env_unset(tmp_servers_root, monkeypatch):
    monkeypatch.delenv("FABRICATOR_AUTH_PASSWORD_HASH", raising=False)
    assert service.get_password_hash() is None
    service.set_password("file-pw")
    assert service.get_password_hash() is not None
    assert service.verify_password("file-pw") is True


def test_set_password_preserves_secret_key(tmp_servers_root, monkeypatch):
    monkeypatch.delenv("SECRET_KEY", raising=False)
    key = service.load_or_create_secret_key()  # persists a key first
    service.set_password("pw")                  # must not clobber the key
    data = json.loads((tmp_servers_root / "auth.json").read_text(encoding="utf-8"))
    assert data["secret_key"] == key
    assert "password_hash" in data
    assert service.load_or_create_secret_key() == key


def test_complete_setup_one_time(tmp_servers_root, monkeypatch):
    monkeypatch.delenv("FABRICATOR_AUTH_PASSWORD_HASH", raising=False)
    assert service.complete_setup("first-pw") is True
    assert service.verify_password("first-pw") is True
    # Second call refuses and does NOT overwrite the credential.
    assert service.complete_setup("second-pw") is False
    assert service.verify_password("first-pw") is True
    assert service.verify_password("second-pw") is False


def test_complete_setup_false_when_env_hash_present(tmp_servers_root, monkeypatch):
    monkeypatch.setenv("FABRICATOR_AUTH_PASSWORD_HASH", service.hash_password("env"))
    assert service.complete_setup("anything") is False


def test_auth_file_is_0600(tmp_servers_root, monkeypatch):
    monkeypatch.delenv("SECRET_KEY", raising=False)
    service.load_or_create_secret_key()
    mode = stat.S_IMODE((tmp_servers_root / "auth.json").stat().st_mode)
    assert mode == 0o600


# --------------------------------------------------------------------------- #
# Session signing key (env > file > generate+persist)
# --------------------------------------------------------------------------- #

def test_secret_key_env_overrides(tmp_servers_root, monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "env-key")
    assert service.load_or_create_secret_key() == "env-key"
    # An env override must not persist a file.
    assert not (tmp_servers_root / "auth.json").exists()


def test_secret_key_generated_and_stable(tmp_servers_root, monkeypatch):
    monkeypatch.delenv("SECRET_KEY", raising=False)
    k1 = service.load_or_create_secret_key()
    assert k1 and len(k1) >= 32
    assert service.load_or_create_secret_key() == k1  # persisted + stable


def test_data_dir_writable_true(tmp_servers_root):
    assert service.data_dir_writable() is True
