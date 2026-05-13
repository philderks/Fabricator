"""B8: ``parse_java_major`` correctly extracts the Java major version.

Covers the consolidation of duplicate parsers from
``server/manager.py:_resolve_java_major`` and the inline regex in
``server/routes.py:get_java_status``.
"""
from __future__ import annotations

import pytest

from backend.utils.java import parse_java_major


@pytest.mark.parametrize(
    "version_output,expected",
    [
        # Legacy 1.x.y format -> y is the major.
        ('java version "1.8.0_362"', 8),
        ('openjdk version "1.8.0_402" 2024-01-16', 8),
        # Modern numeric majors.
        ('openjdk version "17.0.5" 2022-10-18', 17),
        ('openjdk version "21" 2023-09-19', 21),
        ('java version "11.0.20" 2023-07-18 LTS', 11),
        # Output the parser cannot make sense of.
        ("", None),
        ("invalid string", None),
        # Malformed quoted version (no digits at start).
        ('java version "abc"', None),
    ],
)
def test_parse_java_major_known_outputs(version_output, expected):
    assert parse_java_major(version_output) == expected


def test_parse_java_major_legacy_without_minor_returns_none():
    """Legacy ``1.`` prefix without a numeric minor is unparseable."""
    assert parse_java_major('java version "1."') is None
    assert parse_java_major('java version "1.x"') is None
