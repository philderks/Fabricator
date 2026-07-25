"""Managed-mode config helpers: is_managed / managed_memory_gb / ManagedConfigError.

Off by default (fail-safe): a self-hoster who never sets FABRICATOR_MANAGED sees
False, and managed_memory_gb() returns None (the fail-closed signal) until an
explicit positive integer is set.
"""
from __future__ import annotations

from backend.managed import ManagedConfigError, is_managed, managed_memory_gb


def test_is_managed_default_false(monkeypatch):
    monkeypatch.delenv("FABRICATOR_MANAGED", raising=False)
    assert is_managed() is False


def test_is_managed_true_for_one(monkeypatch):
    monkeypatch.setenv("FABRICATOR_MANAGED", "1")
    assert is_managed() is True


def test_is_managed_true_case_insensitive(monkeypatch):
    monkeypatch.setenv("FABRICATOR_MANAGED", "TRUE")
    assert is_managed() is True


def test_is_managed_false_for_zero(monkeypatch):
    monkeypatch.setenv("FABRICATOR_MANAGED", "0")
    assert is_managed() is False


def test_is_managed_false_for_garbage(monkeypatch):
    monkeypatch.setenv("FABRICATOR_MANAGED", "banana")
    assert is_managed() is False


def test_managed_memory_gb_unset_is_none(monkeypatch):
    monkeypatch.delenv("FABRICATOR_MANAGED_MEMORY_GB", raising=False)
    assert managed_memory_gb() is None


def test_managed_memory_gb_valid_positive(monkeypatch):
    monkeypatch.setenv("FABRICATOR_MANAGED_MEMORY_GB", "6")
    assert managed_memory_gb() == 6


def test_managed_memory_gb_zero_is_none(monkeypatch):
    monkeypatch.setenv("FABRICATOR_MANAGED_MEMORY_GB", "0")
    assert managed_memory_gb() is None


def test_managed_memory_gb_negative_is_none(monkeypatch):
    monkeypatch.setenv("FABRICATOR_MANAGED_MEMORY_GB", "-4")
    assert managed_memory_gb() is None


def test_managed_memory_gb_noninteger_is_none(monkeypatch):
    monkeypatch.setenv("FABRICATOR_MANAGED_MEMORY_GB", "4.5")
    assert managed_memory_gb() is None


def test_managed_config_error_is_exception():
    assert issubclass(ManagedConfigError, Exception)
