"""Shared string helpers for backend code."""
import re

_TRUTHY_VALUES = frozenset({"1", "true", "yes", "on"})

_SLUG_NONALNUM_RE = re.compile(r"[^a-z0-9]+")


def bool_from_str(value: str | None) -> bool:
    """Return True for canonical truthy strings, False otherwise.

    Truthy: ``"1"``, ``"true"``, ``"yes"``, ``"on"`` (case-insensitive,
    surrounding whitespace trimmed). ``None`` and any other string return
    ``False``. Used by Modrinth route helpers and the Java-compat env flag.
    """
    if value is None:
        return False
    return value.strip().lower() in _TRUTHY_VALUES


def slugify(value: str | None, *, fallback: str = "") -> str:
    """Return a filesystem-safe lowercase slug for ``value``.

    Collapses runs of non-alphanumeric characters to single ``-`` and
    strips leading/trailing dashes. Empty result falls back to
    ``fallback`` so callers always get a usable name. Used by the backup
    service to embed config names in archive filenames without quoting.
    """
    if value is None:
        return fallback
    slug = _SLUG_NONALNUM_RE.sub("-", str(value).lower()).strip("-")
    return slug or fallback
