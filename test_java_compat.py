"""Tests for Minecraft-to-Java compatibility mapping."""

import pytest

from backend.server.java_compat import resolve_required_java, skip_java_enforcement


def test_legacy_and_modern_version_rules():
    assert resolve_required_java("1.8.9").required_java == 8
    assert resolve_required_java("1.16.5").required_java == 8
    assert resolve_required_java("1.17.1").required_java == 16
    assert resolve_required_java("1.20.4").required_java == 17
    assert resolve_required_java("1.20.5").required_java == 21
    assert resolve_required_java("1.21.6").required_java == 21
    assert resolve_required_java("1.26.1").required_java == 25


def test_gap_versions_are_warning_only():
    compat = resolve_required_java("1.24.3")
    assert compat.required_java is None
    assert compat.warning is not None
    assert compat.enforceable is False


def test_unparseable_versions_return_low_confidence_warning():
    compat = resolve_required_java("snapshot-foo")
    assert compat.required_java is None
    assert compat.confidence == "low"
    assert compat.warning is not None


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on"])
def test_skip_java_enforcement_enabled(monkeypatch, value):
    monkeypatch.setenv("FABRICATOR_SKIP_JAVA_CHECK", value)
    assert skip_java_enforcement() is True


def test_skip_java_enforcement_disabled(monkeypatch):
    monkeypatch.delenv("FABRICATOR_SKIP_JAVA_CHECK", raising=False)
    assert skip_java_enforcement() is False
    monkeypatch.setenv("FABRICATOR_SKIP_JAVA_CHECK", "0")
    assert skip_java_enforcement() is False
