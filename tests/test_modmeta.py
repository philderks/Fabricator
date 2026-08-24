"""Dependency-aware removal: who goes, who stays, and who gets dragged out.

Side classification alone is not enough, because mods form a graph. Both
directions of that showed up in issue #64's pack on a real NeoForge server:

* Dropping ``geckolib`` (``client_only_server_optional``) stranded
  ``golem_spawn_animation``, which hard-requires it, and NeoForge refused to
  boot: *"Mod golem_spawn_animation requires geckolib 0 or above. Currently,
  geckolib is not installed"*.
* Keeping something that hard-requires ``sodium`` (``client_only``) would fail
  the same way once Sodium is correctly removed.

The two are resolved in opposite directions, which is what these tests pin.
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from backend.modrinth import modmeta
from backend.modrinth.modmeta import ModIdentity


def forge_jar(tmp_path: Path, name: str, mod_id: str, requires=(), optional=(), provides=()):
    """Build a jar with a NeoForge manifest declaring ids and dependencies."""
    lines = ['modLoader="javafml"', 'loaderVersion="[1,)"', 'license="MIT"',
             "[[mods]]", f'modId="{mod_id}"', 'version="1.0"']
    if provides:
        lines.append("provides=[" + ",".join(f'"{p}"' for p in provides) + "]")
    for dep in requires:
        lines += [f"[[dependencies.{mod_id}]]", f'modId="{dep}"',
                  'type="required"', 'versionRange="[0,)"']
    for dep in optional:
        lines += [f"[[dependencies.{mod_id}]]", f'modId="{dep}"',
                  'type="optional"', 'versionRange="[0,)"']
    path = tmp_path / name
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("META-INF/neoforge.mods.toml", "\n".join(lines))
    return path


def fabric_jar(tmp_path: Path, name: str, mod_id: str, depends=()):
    path = tmp_path / name
    meta = {"id": mod_id, "version": "1.0"}
    if depends:
        meta["depends"] = {d: "*" for d in depends}
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("fabric.mod.json", json.dumps(meta))
    return path


# ---------------------------------------------------------------------------
# Reading identity out of a jar
# ---------------------------------------------------------------------------

def test_forge_identity_reports_ids_and_required_deps(tmp_path):
    jar = forge_jar(tmp_path, "a.jar", "golem_spawn_animation", requires=["geckolib"])
    identity = modmeta.read_identity(jar, "neoforge")
    assert identity.provides == {"golem_spawn_animation"}
    assert identity.requires == {"geckolib"}


def test_optional_dependencies_are_not_binding(tmp_path):
    """An optional dep must not drag a client mod back onto the server."""
    jar = forge_jar(tmp_path, "a.jar", "demo", optional=["sodium"])
    assert modmeta.read_identity(jar, "neoforge").requires == set()


def test_platform_ids_are_ignored(tmp_path):
    """minecraft/neoforge are never files in mods/, so they are noise."""
    jar = forge_jar(tmp_path, "a.jar", "demo", requires=["minecraft", "neoforge", "mru"])
    assert modmeta.read_identity(jar, "neoforge").requires == {"mru"}


def test_provides_counts_as_an_identity(tmp_path):
    """Sodium's NeoForge build provides "indium"; a dep on it is satisfied."""
    jar = forge_jar(tmp_path, "a.jar", "sodium", provides=["indium"])
    assert modmeta.read_identity(jar, "neoforge").provides == {"sodium", "indium"}


def test_fabric_identity(tmp_path):
    jar = fabric_jar(tmp_path, "a.jar", "demo", depends=["geckolib", "minecraft"])
    identity = modmeta.read_identity(jar, "fabric")
    assert identity.provides == {"demo"}
    assert identity.requires == {"geckolib"}


def test_unreadable_jar_is_neutral(tmp_path):
    """Something we cannot read neither protects nor condemns anything."""
    jar = tmp_path / "broken.jar"
    jar.write_bytes(b"not a zip")
    assert modmeta.read_identity(jar, "neoforge") == ModIdentity.empty()


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------

def _ids(**spec):
    """{'path': (provides, requires)} -> identity map."""
    return {p: ModIdentity(set(pr), set(rq)) for p, (pr, rq) in spec.items()}


def test_soft_removal_is_cancelled_when_something_needs_it():
    """The geckolib case, exactly as it failed on the real server."""
    identities = _ids(
        geckolib=({"geckolib"}, set()),
        golem=({"golem_spawn_animation"}, {"geckolib"}),
    )
    removed, spared = modmeta.resolve_removals(identities, hard_client=set(), soft_client={"geckolib"})
    assert removed == set()
    assert spared == {"geckolib"}


def test_soft_removal_stands_when_nothing_needs_it():
    """The Fog case: tagged the same as geckolib, but depended on by nobody."""
    identities = _ids(
        fog=({"fog"}, set()),
        other=({"other"}, set()),
    )
    removed, spared = modmeta.resolve_removals(identities, hard_client=set(), soft_client={"fog"})
    assert removed == {"fog"}
    assert spared == set()


def test_hard_removal_drags_out_its_dependents():
    """A mod that cannot start without a client-only mod cannot start at all."""
    identities = _ids(
        sodium=({"sodium"}, set()),
        addon=({"sodiumextra"}, {"sodium"}),
        unrelated=({"lithium"}, set()),
    )
    removed, spared = modmeta.resolve_removals(identities, hard_client={"sodium"}, soft_client=set())
    assert removed == {"sodium", "addon"}
    assert spared == set()


def test_hard_removal_cascades_transitively():
    identities = _ids(
        sodium=({"sodium"}, set()),
        mid=({"mid"}, {"sodium"}),
        top=({"top"}, {"mid"}),
    )
    removed, _ = modmeta.resolve_removals(identities, hard_client={"sodium"}, soft_client=set())
    assert removed == {"sodium", "mid", "top"}


def test_a_soft_mod_needed_only_by_a_doomed_mod_still_goes():
    """Sparing must answer to who actually survives, not who was there.

    ``addon`` requires ``geckolib``, but ``addon`` itself is being dragged out
    for requiring ``sodium``. With nothing left that needs it, geckolib has no
    reason to stay.
    """
    identities = _ids(
        sodium=({"sodium"}, set()),
        addon=({"addon"}, {"sodium", "geckolib"}),
        geckolib=({"geckolib"}, set()),
    )
    removed, spared = modmeta.resolve_removals(
        identities, hard_client={"sodium"}, soft_client={"geckolib"},
    )
    assert "addon" in removed
    assert "geckolib" in removed
    assert spared == set()


def test_nothing_to_remove_is_a_no_op():
    identities = _ids(a=({"a"}, set()), b=({"b"}, {"a"}))
    assert modmeta.resolve_removals(identities, set(), set()) == (set(), set())


def test_a_spared_mod_keeps_providing_for_the_cascade():
    """A spared jar is present, so it must not look 'gone' to the cascade."""
    identities = _ids(
        sodium=({"sodium"}, set()),
        geckolib=({"geckolib"}, set()),
        server_mod=({"server_mod"}, {"geckolib"}),
    )
    removed, spared = modmeta.resolve_removals(
        identities, hard_client={"sodium"}, soft_client={"geckolib"},
    )
    assert spared == {"geckolib"}
    assert removed == {"sodium"}
    assert "server_mod" not in removed
