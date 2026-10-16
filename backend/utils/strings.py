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


# A backslash that does not start one of the two escapes MOTDs were hand-typed
# with before the editor existed (``\uXXXX`` and ``\n``).
_STRAY_BACKSLASH_RE = re.compile(r"\\(?!u[0-9a-fA-F]{4}|n)")

_PROPERTIES_ESCAPE_RE = re.compile(r"\\(u[0-9a-fA-F]{4}|.)", re.S)
_PROPERTIES_CONTROLS = {"t": "\t", "n": "\n", "r": "\r", "f": "\f"}


def escape_properties_value(value: str, *, keep_leading_space: bool = False) -> str:
    """Return ``value`` escaped for a ``key=value`` line Java's Properties reads.

    Newlines would otherwise end the line (a two-line MOTD turns its second
    line into a junk key), and raw non-ASCII such as ``§`` reads as ``Â§`` on
    Minecraft versions that load server.properties as ISO-8859-1, so both are
    escaped; ``\\uXXXX`` decodes the same on every version. Backslashes are
    doubled so they survive (a raw one could swallow the next line or, as in
    ``C:\\users``, make Minecraft refuse the whole file), except where they
    start a ``\\uXXXX`` or ``\\n`` escape: MOTDs written with that old
    hand-typed workaround keep meaning what they meant.

    Java strips leading whitespace from every value. ``keep_leading_space``
    escapes it instead; only the MOTD wants that (hand-centered lines), since
    for keys like level-name or server-ip the stripping is what Fabricator and
    Minecraft both rely on.
    """
    out = []
    for ch in _STRAY_BACKSLASH_RE.sub(r"\\\\", str(value)):
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
    if keep_leading_space and escaped[:1] in (" ", "\t", "\f"):
        return "\\" + escaped
    return escaped


def unescape_properties_value(value: str) -> str:
    """Decode a raw server.properties value the way Java's Properties does.

    The counterpart of :func:`escape_properties_value` for Fabricator's own
    readers of the file, which would otherwise see ``w\\u00E9lt`` where
    Minecraft sees ``wélt``. Surrogate-pair escapes are joined back up.
    """
    def decode(match: re.Match) -> str:
        escape = match.group(1)
        if len(escape) == 5:
            return chr(int(escape[1:], 16))
        return _PROPERTIES_CONTROLS.get(escape, escape)

    decoded = _PROPERTIES_ESCAPE_RE.sub(decode, value)
    return decoded.encode("utf-16", "surrogatepass").decode("utf-16", "surrogatepass")
