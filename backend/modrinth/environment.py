"""Ask Modrinth what side a mod runs on, instead of guessing from its jar.

Modrinth used to describe a project's sides with two independent fields,
``client_side`` and ``server_side``, each ``required`` / ``optional`` /
``unsupported``. Nine of those combinations were meaningless and authors
mislabelled their mods constantly, so Modrinth deprecated both in favour of
one ``environment`` list with named, unambiguous values. Despite the field
being introduced for the experimental v3 API, v2 already serves it, so
Fabricator can use it without leaving the API it is built on.

Why this outranks every signal Fabricator can read out of a jar: those
signals are inference, and issue #64 is what inference costs. Sodium's
NeoForge jar declares no mod-level ``side`` in ``neoforge.mods.toml`` (only
its dependency entries carry ``side = "CLIENT"``, which describes the
dependency and not Sodium), and the real code lives in a nested Jar-in-Jar
that a surface scan never opens. Fabricator concluded "uncertain", installed
it, and NeoForge crashed on ``org/lwjgl/Version`` during early loading before
any side check could run. Modrinth, meanwhile, reports ``client_only`` —
stated by the author, and correct.

The lookup is by file hash, not project name: the modpack index gives a sha1
for every file it lists, and a hash resolves to exactly one Modrinth version,
so a repackaged or renamed jar cannot be mistaken for something else. Results
flow through the same caches the mods page uses (:mod:`backend.modrinth.installed`),
which makes a whole pack cost about two requests.

Nothing here is allowed to break an install. Modrinth being down, rate
limited, or simply not knowing a jar all resolve to "uncertain", which leaves
the existing jar heuristics in charge exactly as before.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, List, NamedTuple, Optional

from backend.modrinth.installed import resolve_projects, resolve_versions

logger = logging.getLogger(__name__)

# Environments Fabricator will not put on a dedicated server.
#
# ``singleplayer_only`` is documented as not functioning in multiplayer, which
# is the only thing Fabricator builds.
#
# ``client_only_server_optional`` is here because *optional on the server is
# not a reason to install*. The client is the required side, so skipping costs
# the user an optional enhancement they can still add by hand, while installing
# can stop the server booting: Fog is tagged this way, ships
# ``net/minecraft/client/KeyMapping``, and dies on a dedicated server with
# "Attempted to load class ... for invalid dist DEDICATED_SERVER". Every value
# left in the server set below has the server as a required or fully
# functional side; this one does not.
CLIENT_ONLY_ENVIRONMENTS = frozenset({
    "client_only",
    "client_only_server_optional",
    "singleplayer_only",
})

# Of those, the ones the server merely does not *need*. They are safe to load,
# so if a surviving mod hard-requires one it is kept rather than stranding the
# dependent — see :func:`backend.modrinth.modmeta.resolve_removals`. The rest
# are hard: a dedicated server cannot run them at all.
SOFT_CLIENT_ENVIRONMENTS = frozenset({
    "client_only_server_optional",
})


class Verdict(NamedTuple):
    """A side decision, plus the environment tag it came from.

    The tag matters downstream: "the server does not need this" and "the
    server cannot run this" are both ``client``, but they are resolved in
    opposite directions when another mod depends on the jar.
    """

    side: str
    reason: str
    tag: str = ""

    @property
    def is_soft(self) -> bool:
        return self.tag in SOFT_CLIENT_ENVIRONMENTS

# Environments a dedicated server can load and actually use.
SERVER_CAPABLE_ENVIRONMENTS = frozenset({
    "client_and_server",
    "client_or_server",
    "client_or_server_prefers_both",
    "dedicated_server_only",
    "server_only",
    "server_only_client_optional",
})


def _tags(values: Any) -> List[str]:
    """Normalize an ``environment`` payload into a list of lowercase tags."""
    if isinstance(values, str):
        candidates: Iterable[Any] = [values]
    elif isinstance(values, (list, tuple, set)):
        candidates = values
    else:
        return []
    return [t for t in (str(v or "").strip().lower() for v in candidates) if t]


def side_from_environment(values: Any) -> Verdict:
    """Classify a project's ``environment`` list as client / server / uncertain.

    A server-capable value wins over a client-only one when both appear. That
    only matters for a project tagged inconsistently, and there the safe error
    is to install a mod the server can load, not to strip one it needs —
    over-eager skipping is its own bug (issue #58).
    """
    tags = _tags(values)
    if not tags:
        return Verdict("uncertain", "")

    for tag in tags:
        if tag in SERVER_CAPABLE_ENVIRONMENTS:
            return Verdict("server", f"Modrinth environment={tag}", tag)

    for tag in tags:
        if tag in CLIENT_ONLY_ENVIRONMENTS:
            return Verdict("client", f"Modrinth environment={tag}", tag)

    # ``unknown``, or a value added after this table was written. Either way
    # Modrinth has nothing to say, so the jar heuristics stay in charge.
    return Verdict("uncertain", "")


def side_from_project(project: Dict[str, Any]) -> Verdict:
    """Resolve one project's install side, newest metadata first.

    Falls back to the deprecated ``server_side`` field when ``environment``
    is absent or uninformative, which covers a project whose metadata has not
    been migrated and any third-party Labrinth instance still on the old
    schema.
    """
    verdict = side_from_environment(project.get("environment"))
    if verdict.side != "uncertain":
        return verdict

    server_side = str(project.get("server_side") or "").strip().lower()
    if server_side == "unsupported":
        return Verdict("client", "Modrinth server_side=unsupported")
    if server_side in ("required", "optional"):
        return Verdict("server", f"Modrinth server_side={server_side}")

    return Verdict("uncertain", "")


def sides_by_hash(
    client: Any, hashes: List[str], algorithm: str = "sha1"
) -> Dict[str, Verdict]:
    """Resolve ``hashes`` to ``{hash: (side, reason)}`` via Modrinth.

    Hashes Modrinth does not recognise, and projects it has no side metadata
    for, are simply absent from the result — the caller treats a missing
    entry as "no opinion" and falls back to its own heuristics.

    Never raises. A lookup failure is logged and returns ``{}`` so a Modrinth
    outage degrades classification instead of failing the install.
    """
    wanted = [h for h in hashes if h]
    if not wanted:
        return {}

    try:
        versions = resolve_versions(client, wanted, algorithm=algorithm)
        projects = resolve_projects(
            client,
            [v.get("project_id") for v in versions.values() if v.get("project_id")],
        )
    except Exception as exc:  # noqa: BLE001 - classification is best-effort
        logger.warning("modrinth: side lookup failed, falling back to jar metadata: %s", exc)
        return {}

    sides: Dict[str, Verdict] = {}
    for digest, version in versions.items():
        project = projects.get(version.get("project_id"))
        if not project:
            continue
        verdict = side_from_project(project)
        if verdict.side == "uncertain":
            continue
        title = project.get("title") or project.get("slug")
        sides[digest] = verdict._replace(
            reason=verdict.reason + (f" ({title})" if title else "")
        )
    return sides


def sides_by_path(
    client: Any,
    hashes_by_path: Dict[str, str],
    algorithm: str = "sha1",
) -> Dict[str, Verdict]:
    """Same as :func:`sides_by_hash`, keyed by install path rather than hash."""
    if not hashes_by_path:
        return {}
    sides = sides_by_hash(client, list(hashes_by_path.values()), algorithm=algorithm)
    if not sides:
        return {}
    resolved: Dict[str, Verdict] = {}
    for path, digest in hashes_by_path.items():
        verdict: Optional[Verdict] = sides.get((digest or "").lower())
        if verdict is not None:
            resolved[path] = verdict
    return resolved
