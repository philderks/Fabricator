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


def escape_properties_value(value: str) -> str:
    """Return ``value`` escaped for a ``key=value`` line Java's Properties reads.

    Newlines would otherwise end the line (a two-line MOTD turns its second
    line into a junk key), and raw non-ASCII such as ``§`` reads as ``Â§`` on
    Minecraft versions that load server.properties as ISO-8859-1, so both are
    escaped; ``\\uXXXX`` decodes the same on every version. A leading space is
    escaped too, since Java strips unescaped leading whitespace. Backslashes
    are deliberately left alone: MOTDs written with the old hand-typed
    ``\\u00A7`` / ``\\n`` workaround keep meaning what they meant, at the cost
    of a literal backslash never surviving (as before).
    """
    out = []
    for ch in str(value):
        if ch == "\n":
            out.append("\\n")
        elif ch == "\r":
            out.append("\\r")
        elif ord(ch) > 0x7E:
            units = ch.encode("utf-16-be")
            out.extend(f"\\u{units[i]:02X}{units[i + 1]:02X}" for i in range(0, len(units), 2))
        else:
            out.append(ch)
    escaped = "".join(out)
    return "\\" + escaped if escaped[:1] in (" ", "\t", "\f") else escaped
