"""Loader-aware mod-jar classification tests.

Pins the behavior of ``ModrinthClient._classify_mod_jar_for_server`` once
it understands Quilt and Forge/NeoForge metadata in addition to the
existing Fabric reader. Each test covers one distinct behavior — the
suite is intentionally narrow (Quilt: 5, Forge/NeoForge: 6, dispatch:
3) per the loader-architecture plan.

Reader precedence (HARD LOCK from plan, mirrored here so a regression
in the implementation surfaces as a failing test, not as silent drift):

* ``fabric``   -> ``fabric.mod.json`` only
* ``quilt``    -> ``quilt.mod.json`` first; fall back to ``fabric.mod.json``
* ``forge``    -> ``META-INF/mods.toml`` only (NeoForge file ignored)
* ``neoforge`` -> ``META-INF/neoforge.mods.toml`` first; fall back to
  ``META-INF/mods.toml``

Forge/NeoForge mod-side signals honored: top-level ``clientSideOnly``
and the ``[[mods]]`` table's ``side`` field. ``[[dependencies.<modid>]]``
``side`` is intentionally ignored — it describes the dependency's
side-context, not the host mod's.
"""
from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Dict, Optional, Union

import pytest

from backend.modrinth.client import ModrinthClient


def make_mod_jar(
    tmp_path: Path,
    metadata_files: Dict[str, Union[str, bytes]],
    class_files: Optional[Dict[str, bytes]] = None,
    name: str = "mod.jar",
) -> Path:
    """Build a synthetic .jar with given metadata + optional class files."""
    jar_path = tmp_path / name
    with zipfile.ZipFile(jar_path, "w") as zf:
        for arcname, content in metadata_files.items():
            zf.writestr(arcname, content)
        for arcname, content in (class_files or {}).items():
            zf.writestr(arcname, content)
    return jar_path


@pytest.fixture
def mod_client():
    return ModrinthClient()


# ---------------------------------------------------------------------------
# Quilt reader (5)
# ---------------------------------------------------------------------------

def test_quilt_environment_client(mod_client, tmp_path):
    jar = make_mod_jar(tmp_path, {
        "quilt.mod.json": '''{
            "schema_version": 1,
            "quilt_loader": {
                "id": "demo", "version": "1.0.0",
                "minecraft": {"environment": "client"}
            }
        }''',
    })
    classification, _ = mod_client._classify_mod_jar_for_server(jar, loader="quilt")
    assert classification == "client"


def test_quilt_environment_dedicated_server(mod_client, tmp_path):
    """Quilt uses ``dedicated_server`` (NOT ``server``)."""
    jar = make_mod_jar(tmp_path, {
        "quilt.mod.json": '''{
            "schema_version": 1,
            "quilt_loader": {
                "id": "demo", "version": "1.0.0",
                "minecraft": {"environment": "dedicated_server"}
            }
        }''',
    })
    classification, _ = mod_client._classify_mod_jar_for_server(jar, loader="quilt")
    assert classification == "server"


def test_quilt_environment_universal(mod_client, tmp_path):
    jar = make_mod_jar(tmp_path, {
        "quilt.mod.json": '''{
            "schema_version": 1,
            "quilt_loader": {
                "id": "demo", "version": "1.0.0",
                "minecraft": {"environment": "*"}
            }
        }''',
    })
    classification, _ = mod_client._classify_mod_jar_for_server(jar, loader="quilt")
    assert classification == "uncertain"


def test_quilt_falls_back_to_fabric_manifest(mod_client, tmp_path):
    """A Quilt server installing a Fabric-only jar uses fabric.mod.json."""
    jar = make_mod_jar(tmp_path, {
        "fabric.mod.json": '{"id": "demo", "environment": "client"}',
    })
    classification, _ = mod_client._classify_mod_jar_for_server(jar, loader="quilt")
    assert classification == "client"


def test_quilt_missing_or_invalid_manifest(mod_client, tmp_path):
    jar = make_mod_jar(tmp_path, {
        "quilt.mod.json": "{not valid json",
    })
    classification, _ = mod_client._classify_mod_jar_for_server(jar, loader="quilt")
    assert classification == "uncertain"


# ---------------------------------------------------------------------------
# Forge / NeoForge reader (6)
# ---------------------------------------------------------------------------

ENTITYCULLING_MODS_TOML = '''modLoader="javafml"
loaderVersion="[28,)"
clientSideOnly=true
license="tr7zw Protective License"
[[mods]]
modId="entityculling"
version="1.8.2"
displayName="EntityCulling"
'''


def test_forge_top_level_clientsideonly(mod_client, tmp_path):
    """Real-world signal: EntityCulling sets clientSideOnly=true."""
    jar = make_mod_jar(tmp_path, {
        "META-INF/mods.toml": ENTITYCULLING_MODS_TOML,
    })
    classification, _ = mod_client._classify_mod_jar_for_server(jar, loader="forge")
    assert classification == "client"


def test_forge_mods_side_client(mod_client, tmp_path):
    jar = make_mod_jar(tmp_path, {
        "META-INF/mods.toml": '''modLoader="javafml"
loaderVersion="[28,)"
license="MIT"
[[mods]]
modId="demo"
version="1.0"
side="CLIENT"
''',
    })
    classification, _ = mod_client._classify_mod_jar_for_server(jar, loader="forge")
    assert classification == "client"


def test_forge_mods_side_server(mod_client, tmp_path):
    jar = make_mod_jar(tmp_path, {
        "META-INF/mods.toml": '''modLoader="javafml"
loaderVersion="[28,)"
license="MIT"
[[mods]]
modId="demo"
version="1.0"
side="SERVER"
''',
    })
    classification, _ = mod_client._classify_mod_jar_for_server(jar, loader="forge")
    assert classification == "server"


def test_forge_dependencies_side_does_not_classify_host(mod_client, tmp_path):
    """Real-world: ``configured`` declares its ``catalogue`` dep as
    side="CLIENT" but ``configured`` itself is server-compatible. The
    classifier MUST treat the host as uncertain, never as client.
    """
    jar = make_mod_jar(tmp_path, {
        "META-INF/mods.toml": '''modLoader="javafml"
loaderVersion="[39,)"
license="LGPL-3.0"
[[mods]]
modId="configured"
version="2.5.0"
displayName="Configured"
[[dependencies.configured]]
    modId="catalogue"
    mandatory=false
    versionRange="[1.10.1,)"
    ordering="NONE"
    side="CLIENT"
''',
    })
    classification, _ = mod_client._classify_mod_jar_for_server(jar, loader="forge")
    assert classification == "uncertain"


def test_neoforge_prefers_neoforge_mods_toml_over_mods_toml(mod_client, tmp_path):
    """If a jar ships both files, loader=neoforge reads neoforge.mods.toml."""
    jar = make_mod_jar(tmp_path, {
        "META-INF/mods.toml": '''modLoader="javafml"
loaderVersion="[1,)"
[[mods]]
modId="demo"
version="1.0"
side="SERVER"
''',
        "META-INF/neoforge.mods.toml": '''modLoader="javafml"
loaderVersion="[1,)"
[[mods]]
modId="demo"
version="1.0"
side="CLIENT"
''',
    })
    classification, _ = mod_client._classify_mod_jar_for_server(jar, loader="neoforge")
    assert classification == "client"


def test_forge_empty_or_malformed_mods_toml(mod_client, tmp_path):
    jar = make_mod_jar(tmp_path, {
        "META-INF/mods.toml": "this is not = valid [toml",
    })
    classification, _ = mod_client._classify_mod_jar_for_server(jar, loader="forge")
    assert classification == "uncertain"


# ---------------------------------------------------------------------------
# Loader-aware dispatch (3)
# ---------------------------------------------------------------------------

def test_dispatch_cross_compat_jar_loader_fabric_picks_fabric(mod_client, tmp_path):
    """Cross-compat jar (fabric+quilt manifests) with loader=fabric uses fabric."""
    jar = make_mod_jar(tmp_path, {
        "fabric.mod.json": '{"id": "demo", "environment": "client"}',
        "quilt.mod.json": '''{
            "schema_version": 1,
            "quilt_loader": {
                "id": "demo", "version": "1.0.0",
                "minecraft": {"environment": "dedicated_server"}
            }
        }''',
    })
    classification, _ = mod_client._classify_mod_jar_for_server(jar, loader="fabric")
    assert classification == "client"


def test_dispatch_cross_compat_jar_loader_quilt_picks_quilt(mod_client, tmp_path):
    """Same jar, loader=quilt picks the quilt manifest (server side)."""
    jar = make_mod_jar(tmp_path, {
        "fabric.mod.json": '{"id": "demo", "environment": "client"}',
        "quilt.mod.json": '''{
            "schema_version": 1,
            "quilt_loader": {
                "id": "demo", "version": "1.0.0",
                "minecraft": {"environment": "dedicated_server"}
            }
        }''',
    })
    classification, _ = mod_client._classify_mod_jar_for_server(jar, loader="quilt")
    assert classification == "server"


def test_dispatch_forge_ignores_neoforge_file(mod_client, tmp_path):
    """loader=forge MUST NOT read neoforge.mods.toml even if present."""
    jar = make_mod_jar(tmp_path, {
        "META-INF/mods.toml": '''modLoader="javafml"
loaderVersion="[1,)"
[[mods]]
modId="demo"
version="1.0"
side="SERVER"
''',
        "META-INF/neoforge.mods.toml": '''modLoader="javafml"
loaderVersion="[1,)"
[[mods]]
modId="demo"
version="1.0"
side="CLIENT"
''',
    })
    classification, _ = mod_client._classify_mod_jar_for_server(jar, loader="forge")
    assert classification == "server"
