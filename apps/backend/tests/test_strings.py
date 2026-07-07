"""Pin ``bool_from_str`` semantics — canonical truthy set + whitespace handling.

Coverage was previously transitive via Modrinth-route integration tests.
This file pins the contract directly so a refactor to the truthy set or
trim behaviour fails locally instead of surfacing only in a route test.
"""
from __future__ import annotations

import pytest

from backend.utils.strings import bool_from_str


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, False),
        ("", False),
        ("1", True),
        ("0", False),
        ("true", True),
        ("TRUE", True),
        ("  yes ", True),  # whitespace-trim is part of the contract
        ("ON", True),
        ("no", False),
        ("off", False),
        ("enabled", False),  # NOT in the canonical truthy set
        ("yesno", False),
        ("y", False),
    ],
)
def test_bool_from_str_canonical_truthy_set(value, expected):
    assert bool_from_str(value) is expected
