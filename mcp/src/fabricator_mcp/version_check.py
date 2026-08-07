"""One startup probe: is this panel older than the package supports?

The package and the panel version independently, and the realistic skew is a
new package against an un-upgraded panel — `uvx` refetches this on a cache miss,
while the panel is a box somebody has to deliberately update. Skew already fails
honestly at call time (an absent route 403s or 404s), but a bare status code
does not tell anyone *why*, so this says it once, up front.

It warns and continues. It never refuses to start: an old panel still serves
most tools correctly, and refusing would turn a soft degradation into an outage.
"""
from __future__ import annotations

import sys
from typing import Optional

import anyio

from fabricator_mcp.client import PanelClient
from fabricator_mcp.config import PanelConfig
from fabricator_mcp.errors import PanelError

#: The oldest panel this package is known to work against — ONE marker, one
#: place. Bump it only when a change makes an older panel genuinely unusable,
#: not on every release. Panels before this predate the API-token gate entirely,
#: so their operators need to hear about it.
MINIMUM_PANEL_VERSION = "1.1.0"


def parse_version(value: object) -> Optional[tuple[int, ...]]:
    """Return comparable numeric components, or None when there is no version.

    Scheme: dotted numeric release segments — the common prefix of semantic
    versioning and of the panel's own git tags ("v1.0.3"). A leading "v" is
    ignored, and everything from the first "-" or "+" (pre-release or build
    metadata) is dropped, because the only question asked here is "is the panel
    older than X", for which a pre-release of X is close enough to X.

    Anything that does not parse — "unknown", "", a git sha, None — returns
    None and is treated as NO VERSION REPORTED, never as version zero. Treating
    it as zero would warn every user of a source build. This function raises
    nothing: an odd version string must not stop the server from starting.
    """
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    if text[:1] in ("v", "V"):
        text = text[1:]
    for separator in ("-", "+"):
        text = text.split(separator, 1)[0]

    numbers: list[int] = []
    for part in text.split("."):
        if not part.isdigit():
            break  # stop at the first non-numeric segment, keep what came before
        numbers.append(int(part))
    return tuple(numbers) or None


def _padded(left: tuple[int, ...], right: tuple[int, ...]):
    """Compare 1.1 against 1.1.0 as equal rather than as older."""
    width = max(len(left), len(right))
    return (
        left + (0,) * (width - len(left)),
        right + (0,) * (width - len(right)),
    )


def warning_for(
    panel_version: object, minimum: str = MINIMUM_PANEL_VERSION
) -> Optional[str]:
    """The one warning line, or None when there is nothing honest to say."""
    panel = parse_version(panel_version)
    if panel is None:
        # No version reported. Nothing was checked, so nothing is claimed —
        # the same posture check_panel takes.
        return None

    floor = parse_version(minimum)
    if floor is None:
        return None

    panel_padded, floor_padded = _padded(panel, floor)
    if panel_padded >= floor_padded:
        return None

    return (
        f"fabricator-mcp: this panel reports version {str(panel_version).strip()}, "
        f"but this package expects at least {minimum}. Some tools may return 403 "
        f"or 404 until the panel is updated. Starting anyway."
    )


async def _fetch_panel_version(config: PanelConfig, transport) -> Optional[str]:
    client = PanelClient(config, transport=transport)
    try:
        status = await client.get("/api/auth/status")
    except PanelError:
        return None
    finally:
        await client.aclose()
    return status.get("panel_version") if isinstance(status, dict) else None


def warn_if_panel_is_old(
    config: PanelConfig, *, transport=None, stream=None
) -> Optional[str]:
    """Probe the panel once; write one warning line if it is too old.

    Returns the message it wrote, or None. Every failure mode is swallowed: a
    probe that could not complete says nothing about the panel's version, and
    this runs before the server serves anything, so it must not be able to stop
    it. That is why the except clause is broad rather than a list of errors.
    """
    target = stream if stream is not None else sys.stderr
    try:
        version = anyio.run(_fetch_panel_version, config, transport)
    except Exception:  # noqa: BLE001 - a failed probe must never block startup
        return None

    message = warning_for(version)
    if message:
        print(message, file=target)
    return message
