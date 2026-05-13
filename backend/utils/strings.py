"""Shared string helpers for backend code."""

_TRUTHY_VALUES = frozenset({"1", "true", "yes", "on"})


def bool_from_str(value: str | None) -> bool:
    """Return True for canonical truthy strings, False otherwise.

    Truthy: ``"1"``, ``"true"``, ``"yes"``, ``"on"`` (case-insensitive,
    surrounding whitespace trimmed). ``None`` and any other string return
    ``False``. Used by Modrinth route helpers and the Java-compat env flag.
    """
    if value is None:
        return False
    return value.strip().lower() in _TRUTHY_VALUES
