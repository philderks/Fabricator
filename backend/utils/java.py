"""Java version-string parser."""

from __future__ import annotations

import re


_VERSION_QUOTED_RE = re.compile(r'version "([^"]+)"')
_LEADING_DIGITS_RE = re.compile(r"^(\d+)")


def parse_java_major(version_output: str) -> int | None:
    """Extract the Java major version from ``java -version``-style output.

    Examples:
        ``... version "1.8.0_362" ...`` -> 8 (legacy ``1.x.y`` format,
        major version is ``x``).
        ``... version "17.0.5" ...`` -> 17.
        ``... version "21" ...`` -> 21.

    Returns ``None`` if the output does not contain a parseable
    ``version "..."`` token.
    """
    match = _VERSION_QUOTED_RE.search(version_output)
    if not match:
        return None
    raw = match.group(1).strip()
    # Legacy Java 8 and earlier format is ``1.X.Y``; major version is ``X``.
    if raw.startswith("1."):
        parts = raw.split(".")
        if len(parts) > 1 and parts[1].isdigit():
            return int(parts[1])
        return None
    major_match = _LEADING_DIGITS_RE.match(raw)
    if not major_match:
        return None
    return int(major_match.group(1))
