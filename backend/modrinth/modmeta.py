"""What a mod jar calls itself, and what it cannot start without.

The side classifiers answer "does this belong on a server". That is not enough
on its own, because mods form a graph: removing one can strand another that
hard-requires it. Issue #64's pack contains both directions of that problem.

* ``geckolib`` is tagged ``client_only_server_optional`` and would be dropped,
  but ``golem_spawn_animation`` — a genuinely server-side mod — declares it a
  required dependency, and NeoForge refuses to start: *"Mod
  golem_spawn_animation requires geckolib 0 or above. Currently, geckolib is
  not installed"*.
* ``sodium`` is ``client_only`` and must go. Anything that hard-requires it
  cannot run on a dedicated server either, so it has to go with it.

Both need the same information — which jar provides which mod id, and which
ids it requires — so this module reads it once per loader family and leaves the
policy to the caller.

Only *required* dependencies are reported. An optional dependency is by
definition survivable, and treating one as binding would drag client mods back
onto the server through the back door.
"""
from __future__ import annotations

import json
import logging
import sys
import zipfile
from pathlib import Path
from typing import Any, Dict, Iterable, NamedTuple, Set

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - mirrors client.py's import shim
    import tomli as tomllib

logger = logging.getLogger(__name__)

# Ids that name the platform rather than a jar in ``mods/``. A dependency on
# one of these can never be satisfied by keeping a file, so carrying them
# around would only add noise.
PLATFORM_IDS = frozenset({
    "minecraft", "java", "forge", "neoforge", "fabric", "fabricloader",
    "fabric-loader", "quilt_loader", "quilt_base", "quilted_fabric_api",
})


class ModIdentity(NamedTuple):
    """The ids a jar provides, and the ids it cannot start without."""

    provides: Set[str]
    requires: Set[str]

    @classmethod
    def empty(cls) -> "ModIdentity":
        return cls(set(), set())


def _clean(values: Iterable[Any]) -> Set[str]:
    out = set()
    for v in values:
        text = str(v or "").strip().lower()
        if text and text not in PLATFORM_IDS:
            out.add(text)
    return out


def read_identity(jar_path: Path, loader: str | None = None) -> ModIdentity:
    """Read ``jar_path``'s provided and required mod ids.

    Reads whichever manifests the jar actually carries rather than trusting
    ``loader``: a NeoForge pack routinely contains Fabric jars running through
    Sinytra Connector, and their dependencies bind just as hard.

    An unreadable or manifest-less jar yields empty sets — it then neither
    protects anything nor gets dragged out by a cascade, which is the right
    default for something we cannot read.
    """
    provides: Set[str] = set()
    requires: Set[str] = set()

    try:
        with zipfile.ZipFile(jar_path) as zf:
            names = set(zf.namelist())
            for candidate in ("META-INF/neoforge.mods.toml", "META-INF/mods.toml"):
                if candidate in names:
                    p, r = _read_forge_toml(zf.read(candidate))
                    provides |= p
                    requires |= r
                    break
            if "fabric.mod.json" in names:
                p, r = _read_fabric_json(zf.read("fabric.mod.json"))
                provides |= p
                requires |= r
            if "quilt.mod.json" in names:
                p, r = _read_quilt_json(zf.read("quilt.mod.json"))
                provides |= p
                requires |= r
    except (OSError, zipfile.BadZipFile):
        return ModIdentity.empty()

    return ModIdentity(provides, requires)


def _read_forge_toml(raw: bytes) -> tuple[Set[str], Set[str]]:
    """Forge/NeoForge: ``[[mods]]`` ids plus required ``[[dependencies.*]]``."""
    try:
        data = tomllib.loads(raw.decode("utf-8", errors="replace"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError):
        return set(), set()

    provides: Set[str] = set()
    mods = data.get("mods")
    if isinstance(mods, list):
        for entry in mods:
            if isinstance(entry, dict):
                provides |= _clean([entry.get("modId")])
                # ``provides`` lets a jar stand in for another mod id — Sodium's
                # NeoForge build provides "indium", for instance.
                extra = entry.get("provides")
                if isinstance(extra, list):
                    provides |= _clean(extra)

    requires: Set[str] = set()
    deps = data.get("dependencies")
    if isinstance(deps, dict):
        for entries in deps.values():
            if not isinstance(entries, list):
                continue
            for dep in entries:
                if not isinstance(dep, dict):
                    continue
                # Newer manifests say type="required"; older ones mandatory=true.
                dep_type = str(dep.get("type") or "").strip().lower()
                mandatory = dep.get("mandatory")
                if dep_type == "required" or mandatory is True:
                    requires |= _clean([dep.get("modId")])

    return provides, requires


def _read_fabric_json(raw: bytes) -> tuple[Set[str], Set[str]]:
    """Fabric: ``id``/``provides`` plus the ``depends`` block."""
    try:
        meta = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return set(), set()
    if not isinstance(meta, dict):
        return set(), set()

    provides = _clean([meta.get("id")])
    extra = meta.get("provides")
    if isinstance(extra, list):
        provides |= _clean(extra)

    depends = meta.get("depends")
    requires = _clean(depends.keys()) if isinstance(depends, dict) else set()
    return provides, requires


def _read_quilt_json(raw: bytes) -> tuple[Set[str], Set[str]]:
    """Quilt: ``quilt_loader.id``/``provides`` plus ``depends``."""
    try:
        meta = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return set(), set()
    if not isinstance(meta, dict):
        return set(), set()

    block = meta.get("quilt_loader")
    if not isinstance(block, dict):
        return set(), set()

    provides = _clean([block.get("id")])
    extra = block.get("provides")
    if isinstance(extra, list):
        provides |= _clean(
            e.get("id") if isinstance(e, dict) else e for e in extra
        )

    requires: Set[str] = set()
    depends = block.get("depends")
    if isinstance(depends, list):
        for dep in depends:
            if isinstance(dep, str):
                requires |= _clean([dep])
            elif isinstance(dep, dict) and not dep.get("optional"):
                requires |= _clean([dep.get("id")])

    return provides, requires


def resolve_removals(
    identities: Dict[str, ModIdentity],
    hard_client: Set[str],
    soft_client: Set[str],
) -> tuple[Set[str], Set[str]]:
    """Decide what actually gets removed, honouring the dependency graph.

    ``identities`` maps a path to what that jar provides and requires.
    ``hard_client`` are paths that cannot run on a dedicated server at all;
    ``soft_client`` are paths the server does not need but could tolerate.

    Two opposite rules, because the two cases fail in opposite directions:

    * A **soft** removal is cancelled when a surviving mod requires it —
      dropping it would strand the dependent (``geckolib``).
    * A **hard** removal drags its dependents out with it — a mod that cannot
      start without a client-only mod cannot start on a server either
      (``sodium``).

    Both run to a fixed point, since sparing or removing one jar changes what
    the remaining ones require. Returns ``(removed, spared)``.
    """
    def _provided(paths: Set[str]) -> Set[str]:
        ids: Set[str] = set()
        for path in paths:
            ids |= identities.get(path, ModIdentity.empty()).provides
        return ids

    def _required(paths: Set[str]) -> Set[str]:
        ids: Set[str] = set()
        for path in paths:
            ids |= identities.get(path, ModIdentity.empty()).requires
        return ids

    # Doom first, spare second. A hard removal is not negotiable, so settling
    # it before asking who still needs the soft ones stops a mod being spared
    # on behalf of a dependent that is itself on the way out. Doomed only ever
    # grows, so this terminates.
    doomed = set(hard_client)
    while True:
        cascade = {
            path for path in (set(identities) - doomed)
            if identities[path].requires & _provided(doomed)
        }
        if not cascade:
            break
        doomed |= cascade

    # Now cancel soft removals that a genuine survivor still requires. This
    # set only ever shrinks, so it terminates too.
    soft_removed = set(soft_client) - doomed
    while True:
        survivors = set(identities) - doomed - soft_removed
        needed = _required(survivors)
        rescue = {
            path for path in soft_removed
            if identities.get(path, ModIdentity.empty()).provides & needed
        }
        if not rescue:
            break
        soft_removed -= rescue

    removed = doomed | soft_removed
    spared = set(soft_client) - removed
    return removed, spared
