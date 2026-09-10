"""Tick-rate (TPS) probing: which console command to ask, and how to read the reply.

Minecraft has no machine-readable tick-rate channel, so the only way to learn a
running server's TPS is to type a command into its console and parse the answer
out of stdout. Which command exists depends on the loader, and on vanilla-family
servers also on the version — hence :func:`probe_for`, which returns ``None``
when the running server simply cannot answer (older vanilla/Fabric/Quilt), so
the caller can skip sampling entirely instead of logging an "Unknown command"
error into the user's console every few seconds.

Kept as pure functions in their own module because the interesting part is the
per-loader trivia, and that is far easier to test as a table than through a live
process.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional, Tuple

# Reading kinds returned by classify(). Only TPS_VALUE and MSPT carry a number
# the caller turns into a tick rate; the others exist so the caller can follow
# (TARGET_RATE) and suppress (NOISE) the rest of a multi-line probe reply.
TPS_VALUE = "tps"
TARGET_RATE = "target"
MSPT = "mspt"
NOISE = "noise"

# Vanilla's default tick rate, and the ceiling for a rate derived from ms/tick:
# a server that finishes ticks early still only runs 20 a second.
DEFAULT_TICK_RATE = 20.0

# Loaders whose Bukkit lineage gives them the Spigot ``tps`` command.
_PAPER_FAMILY = frozenset({"paper", "folia", "purpur", "pufferfish", "spigot", "bukkit", "craftbukkit"})

# Vanilla-family loaders: no TPS command of their own, so they inherit whatever
# vanilla ships — i.e. ``/tick query`` from 1.20.3 onward and nothing before it.
_VANILLA_FAMILY = frozenset({"vanilla", "fabric", "quilt"})

# First release with the ``/tick`` command. Below this, vanilla-family servers
# have no way to report a tick rate at all.
_TICK_COMMAND_SINCE = (1, 20, 3)

# Legacy Minecraft versions ("1.21.4"); Mojang's year-based scheme (26.x) is
# handled separately in _supports_tick_command since every such release is
# newer than the cutoff.
_VERSION_RE = re.compile(r"^\s*(\d+)\.(\d+)(?:\.(\d+|x|X))?")

# Bukkit colour codes (§a, §6, …) wrap Paper's reply. Unlike the ANSI escapes
# the caller already strips, these travel as ordinary characters in the log line.
_SECTION_RE = re.compile(r"§.")

# Cheap pre-filter: run the real patterns only on lines that could plausibly be
# part of a reply. This runs on EVERY stdout line of a running server, so the
# common case has to stay a single scan.
_MARKER_RE = re.compile(r"TPS|tick|Percentiles|Unknown|game is")

# Paper/Spigot: "TPS from last 1m, 5m, 15m: *20.0, 20.0, 20.0". The leading "*"
# marks a figure Paper considers not yet meaningful (the server has not been up
# for the whole window) — still the best number available, so it is accepted.
_PAPER_RE = re.compile(r"TPS from last 1m[^:]*:\s*\*?\s*([\d.]+)")

# Forge/NeoForge: "Overall: Mean tick time: 3.933 ms. Mean TPS: 20.000". The
# reply also carries a line per dimension; anchoring on "Overall" takes the
# whole-server figure and lets the per-dimension lines fall through to NOISE.
_FORGE_RE = re.compile(r"Overall\b.*?Mean TPS:\s*([\d.]+)")
_FORGE_DIMENSION_RE = re.compile(r"Mean tick time:\s*[\d.]+\s*ms")

# Vanilla /tick query, which reports a target and a mean cost rather than a rate.
# Four lines, verbatim from a 26.2 server:
#   [12:00:00] [Server thread/INFO]: The game is running normally
#   [12:00:00] [Server thread/INFO]: Target tick rate: 20.0 per second.
#   Average time per tick: 0.4ms (Target: 50.0ms)
#   [12:00:00] [Server thread/INFO]: Percentiles: P50: 0.3ms P95: 0.6ms P99: 6.8ms. Sample: 100
#
# Note the third line: vanilla sends the reply as ONE multi-line chat component,
# so log4j prefixes only its first line and the embedded newline leaves the rest
# bare. That bare line is the only one carrying the number.
_TICK_TARGET_RE = re.compile(r"Target tick rate:\s*([\d.]+)")
_TICK_MSPT_RE = re.compile(r"Average time per tick:\s*([\d.]+)\s*ms")
_TICK_PERCENTILE_RE = re.compile(r"Percentiles:\s*P50")
# The reply's opening line: the tick state (normal / frozen / stepping /
# sprinting). Carries no rate, but is part of the reply and so must be
# recognised to be suppressed.
_TICK_STATE_RE = re.compile(r"The game is (?:running|frozen|stepping|sprinting)")

# A server that does not know the command answers with this. Recognised so the
# sampler can count the miss and give up quietly rather than let it repeat.
_UNKNOWN_COMMAND_RE = re.compile(r"Unknown (?:or incomplete )?command", re.IGNORECASE)


@dataclass(frozen=True)
class TpsProbe:
    """The console command that makes a given server report its tick rate."""

    command: str
    #: Loader family the command belongs to — for logging and tests, not dispatch:
    #: classify() recognises every reply shape regardless of which one we asked for.
    kind: str


def _parse_version(version: str) -> Optional[Tuple[int, int, int]]:
    match = _VERSION_RE.match(str(version or ""))
    if not match:
        return None
    patch_raw = match.group(3)
    patch = 0 if patch_raw is None or patch_raw.lower() == "x" else int(patch_raw)
    return int(match.group(1)), int(match.group(2)), patch


def _supports_tick_command(version: str) -> bool:
    parsed = _parse_version(version)
    if not parsed:
        # Snapshots ("24w14a") and empty version strings. Assuming support would
        # trade a silent "—" for a recurring error line in the user's console,
        # so this stays fail-quiet.
        return False
    major, minor, patch = parsed
    if major >= 24:
        # Year-based versioning; every release under it postdates 1.20.3.
        return True
    if major != 1:
        return False
    return (major, minor, patch) >= _TICK_COMMAND_SINCE


def probe_for(loader: Optional[str], version: Optional[str]) -> Optional[TpsProbe]:
    """Return the TPS command for ``loader``/``version``, or None if there is none."""
    name = str(loader or "").strip().lower()
    if not name:
        return None

    if name in _PAPER_FAMILY:
        return TpsProbe(command="tps", kind="paper")

    if name == "forge":
        return TpsProbe(command="forge tps", kind="forge")

    if name == "neoforge":
        # NeoForge only moved its commands out of the "forge" namespace after
        # its 1.20.1 fork point, which still answers to the Forge spelling.
        parsed = _parse_version(version or "")
        if parsed and parsed[:2] == (1, 20) and parsed[2] <= 1:
            return TpsProbe(command="forge tps", kind="forge")
        return TpsProbe(command="neoforge tps", kind="forge")

    if name in _VANILLA_FAMILY:
        if _supports_tick_command(version or ""):
            return TpsProbe(command="tick query", kind="vanilla")
        return None

    return None


def strip_formatting(text: str) -> str:
    """Drop Bukkit § colour codes so a coloured reply still matches."""
    return _SECTION_RE.sub("", text)


def classify(text: str) -> Optional[Tuple[str, float]]:
    """Read one already-ANSI-stripped log line as part of a TPS reply.

    Returns ``(kind, value)`` or ``None`` when the line is unrelated. ``value``
    is meaningful only for TPS_VALUE (a tick rate) and MSPT (milliseconds per
    tick); it is 0.0 for the other kinds.
    """
    if not _MARKER_RE.search(text):
        return None

    text = strip_formatting(text)

    paper = _PAPER_RE.search(text)
    if paper:
        return TPS_VALUE, float(paper.group(1))

    forge = _FORGE_RE.search(text)
    if forge:
        return TPS_VALUE, float(forge.group(1))

    target = _TICK_TARGET_RE.search(text)
    if target:
        return TARGET_RATE, float(target.group(1))

    mspt = _TICK_MSPT_RE.search(text)
    if mspt:
        return MSPT, float(mspt.group(1))

    if (
        _TICK_PERCENTILE_RE.search(text)
        or _TICK_STATE_RE.search(text)
        or _FORGE_DIMENSION_RE.search(text)
    ):
        return NOISE, 0.0

    if _UNKNOWN_COMMAND_RE.search(text):
        return NOISE, 0.0

    return None


def rate_from_mspt(mspt: float, target_rate: float = DEFAULT_TICK_RATE) -> float:
    """Convert vanilla's mean ms/tick into the tick rate it actually sustained.

    Ticks that finish under budget do not make the server run faster than its
    target, so the result is capped there; only overrunning ticks pull it down.
    """
    if target_rate <= 0:
        target_rate = DEFAULT_TICK_RATE
    if mspt <= 0:
        return target_rate
    return min(target_rate, 1000.0 / mspt)
