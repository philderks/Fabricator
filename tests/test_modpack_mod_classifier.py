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


# ---------------------------------------------------------------------------
# Overrides pipeline (3) — pins the end-to-end behavior of
# ``_extract_overrides`` for each classification outcome. The "client"
# case is the regression we care about most: a client-only Forge jar
# shipped under ``overrides/mods/`` must be removed from disk after the
# classifier identifies it. ``server`` and ``uncertain`` pin the other
# two paths so a future refactor can't silently drop a file or leave a
# dangling jar that the install report claims as installed.
# ---------------------------------------------------------------------------

def _build_mrpack_with_override_jar(
    tmp_path: Path, jar_relpath: str, jar_bytes: bytes,
) -> Path:
    """Produce a minimal .mrpack-style zip with one overrides/ jar."""
    pack_path = tmp_path / "pack.mrpack"
    with zipfile.ZipFile(pack_path, "w") as zf:
        zf.writestr("modrinth.index.json", '{"files": []}')
        zf.writestr(f"overrides/{jar_relpath}", jar_bytes)
    return pack_path


def _override_jar_bytes(metadata_files: Dict[str, Union[str, bytes]]) -> bytes:
    """Build an in-memory .jar (zip) with the given metadata members."""
    import io
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for arcname, content in metadata_files.items():
            zf.writestr(arcname, content)
    return buf.getvalue()


def test_overrides_client_jar_removed_from_disk(mod_client, tmp_path):
    """Forge client-only jar in overrides/mods/ must be deleted after extract."""
    install_path = tmp_path / "server"
    install_path.mkdir()
    pack = _build_mrpack_with_override_jar(
        tmp_path, "mods/entityculling.jar",
        _override_jar_bytes({"META-INF/mods.toml": ENTITYCULLING_MODS_TOML}),
    )

    files_installed: list = []
    files_skipped: list = []
    uncertain_mod_files: list = []
    with zipfile.ZipFile(pack) as zf:
        mod_client._extract_overrides(
            zf, install_path, {},
            files_installed, files_skipped, uncertain_mod_files,
            loader="forge",
        )

    extracted = install_path / "mods" / "entityculling.jar"
    assert not extracted.exists(), "client-classified jar must be unlinked"
    assert "overrides/mods/entityculling.jar" not in files_installed
    assert "overrides/mods/entityculling.jar" in files_skipped
    assert uncertain_mod_files == []


def test_overrides_server_jar_kept_and_listed_installed(mod_client, tmp_path):
    """Server-side jar in overrides/mods/ stays on disk and is reported installed."""
    install_path = tmp_path / "server"
    install_path.mkdir()
    server_toml = '''modLoader="javafml"
loaderVersion="[28,)"
license="MIT"
[[mods]]
modId="demo"
version="1.0"
side="SERVER"
'''
    pack = _build_mrpack_with_override_jar(
        tmp_path, "mods/serverthing.jar",
        _override_jar_bytes({"META-INF/mods.toml": server_toml}),
    )

    files_installed: list = []
    files_skipped: list = []
    uncertain_mod_files: list = []
    with zipfile.ZipFile(pack) as zf:
        mod_client._extract_overrides(
            zf, install_path, {},
            files_installed, files_skipped, uncertain_mod_files,
            loader="forge",
        )

    extracted = install_path / "mods" / "serverthing.jar"
    assert extracted.is_file(), "server-classified jar must remain on disk"
    assert "overrides/mods/serverthing.jar" in files_installed
    assert "overrides/mods/serverthing.jar" not in files_skipped
    assert uncertain_mod_files == []


def test_overrides_uncertain_jar_kept_for_modal_review(mod_client, tmp_path):
    """Uncertain jar stays on disk (so the modal can resolve it) but is
    NOT reported as installed — install_modpack raises 409 for these.
    """
    install_path = tmp_path / "server"
    install_path.mkdir()
    # Only a dependency-side declaration — host side is undetermined.
    uncertain_toml = '''modLoader="javafml"
loaderVersion="[39,)"
license="LGPL-3.0"
[[mods]]
modId="configured"
version="2.5.0"
[[dependencies.configured]]
    modId="catalogue"
    mandatory=false
    versionRange="[1.10.1,)"
    ordering="NONE"
    side="CLIENT"
'''
    pack = _build_mrpack_with_override_jar(
        tmp_path, "mods/configured.jar",
        _override_jar_bytes({"META-INF/mods.toml": uncertain_toml}),
    )

    files_installed: list = []
    files_skipped: list = []
    uncertain_mod_files: list = []
    with zipfile.ZipFile(pack) as zf:
        mod_client._extract_overrides(
            zf, install_path, {},
            files_installed, files_skipped, uncertain_mod_files,
            loader="forge",
        )

    extracted = install_path / "mods" / "configured.jar"
    assert extracted.is_file(), "uncertain jar must stay on disk for modal review"
    assert "overrides/mods/configured.jar" not in files_installed
    assert "overrides/mods/configured.jar" not in files_skipped
    assert len(uncertain_mod_files) == 1
    assert uncertain_mod_files[0]["path"] == "overrides/mods/configured.jar"


# ---------------------------------------------------------------------------
# Constant-pool fallback for Forge/NeoForge (4) — when ``mods.toml`` is
# silent (the common case for client-only Forge mods like ETF, ModernUI,
# Dynamic FPS), scan ``.class`` bytes for known client-only package
# references. A hit promotes the jar from ``uncertain`` to ``client``;
# no hit leaves the metadata reader's ``uncertain`` verdict untouched.
# Gated on loader in {forge, neoforge} AND metadata == uncertain so it
# never overrides an explicit ``side="SERVER"``.
# ---------------------------------------------------------------------------

EMPTY_FORGE_TOML = '''modLoader="javafml"
loaderVersion="[28,)"
license="MIT"
[[mods]]
modId="demo"
version="1.0"
'''


def test_forge_class_pool_lwjgl_hit_classifies_client(mod_client, tmp_path):
    """A .class referencing org/lwjgl/glfw/* in its constant pool -> client."""
    jar = make_mod_jar(
        tmp_path,
        {"META-INF/mods.toml": EMPTY_FORGE_TOML},
        class_files={
            "com/example/Demo.class": b"\xca\xfe\xba\xbeorg/lwjgl/glfw/GLFWErrorCallbackI",
        },
    )
    classification, reason = mod_client._classify_mod_jar_for_server(jar, loader="forge")
    assert classification == "client"
    assert "org/lwjgl/glfw/" in reason


def test_forge_class_pool_no_client_refs_stays_uncertain(mod_client, tmp_path):
    """A clean .class (only safe refs) does not trigger the fallback."""
    jar = make_mod_jar(
        tmp_path,
        {"META-INF/mods.toml": EMPTY_FORGE_TOML},
        class_files={
            "com/example/Demo.class": b"\xca\xfe\xba\xbejava/lang/String",
        },
    )
    classification, _ = mod_client._classify_mod_jar_for_server(jar, loader="forge")
    assert classification == "uncertain"


def test_forge_class_pool_skipped_when_metadata_decided(mod_client, tmp_path):
    """side="SERVER" in mods.toml short-circuits — class scan must NOT run."""
    server_toml_with_client_class = '''modLoader="javafml"
loaderVersion="[28,)"
license="MIT"
[[mods]]
modId="demo"
version="1.0"
side="SERVER"
'''
    jar = make_mod_jar(
        tmp_path,
        {"META-INF/mods.toml": server_toml_with_client_class},
        class_files={
            "com/example/Demo.class": b"\xca\xfe\xba\xbeorg/lwjgl/glfw/GLFW",
        },
    )
    classification, _ = mod_client._classify_mod_jar_for_server(jar, loader="forge")
    assert classification == "server"


def test_forge_class_pool_any_hit_in_mixed_jar_wins(mod_client, tmp_path):
    """First .class with a client ref wins, even when others are clean."""
    jar = make_mod_jar(
        tmp_path,
        {"META-INF/mods.toml": EMPTY_FORGE_TOML},
        class_files={
            "com/example/Clean.class": b"\xca\xfe\xba\xbejava/lang/String",
            "com/example/Renderer.class": b"\xca\xfe\xba\xbenet/minecraft/client/renderer/RenderType",
            "com/example/AlsoClean.class": b"\xca\xfe\xba\xbejava/util/List",
        },
    )
    classification, reason = mod_client._classify_mod_jar_for_server(jar, loader="forge")
    assert classification == "client"
    assert "net/minecraft/client/renderer/" in reason


def test_forge_uncertain_metadata_and_empty_scan_concatenate_reasons(mod_client, tmp_path):
    """When metadata is uncertain AND the class scan finds nothing, the
    final reason must surface BOTH the metadata cause and the scan result
    so the user sees why classification failed at both layers."""
    jar = make_mod_jar(
        tmp_path,
        # No mods.toml at all -> metadata reason is "META-INF/mods.toml missing"
        {},
        class_files={
            "com/example/Demo.class": b"\xca\xfe\xba\xbejava/lang/String",
        },
    )
    classification, reason = mod_client._classify_mod_jar_for_server(jar, loader="forge")
    assert classification == "uncertain"
    assert "mods.toml" in reason
    assert "class references" in reason


# ---------------------------------------------------------------------------
# End-to-end install pipeline (2) — exercises ``_install_index_files`` with
# a stubbed download step so the classifier output flows through the real
# partition logic. These pin that index-driven and metadata-driven skips
# both end up in ``files_skipped`` with the matching jar deleted from disk,
# and that ``files_installed``/``uncertain_mod_files`` agree.
# ---------------------------------------------------------------------------

def _stub_download_with_payloads(monkeypatch, payloads: Dict[str, bytes]) -> None:
    """Patch ``_download_and_verify`` to write ``payloads[url]`` to ``target``.

    Skips real HTTP and hash-checking so a synthetic jar can drive the
    classifier path inside the install pipeline.
    """
    def fake_download(self, url, target, hashes, error_context):  # noqa: ARG001
        target.write_bytes(payloads[url])

    monkeypatch.setattr(ModrinthClient, "_download_and_verify", fake_download)


def test_install_e2e_filters_client_mods_from_index(mod_client, tmp_path, monkeypatch):
    """Two forge index entries: one client-only, one uncertain-but-server.

    Pipeline must skip the client jar (deleted from disk) and install the
    uncertain one because the index declares ``env.server=required`` (the
    saving fallback inside ``_classify_installed_mod``).
    """
    install_path = tmp_path / "server"
    install_path.mkdir()

    client_jar_bytes = _override_jar_bytes({"META-INF/mods.toml": ENTITYCULLING_MODS_TOML})
    # _override_jar_bytes only accepts metadata; build the uncertain jar
    # inline so it ships a clean .class (constant-pool scan finds no client
    # refs) on top of an empty mods.toml.
    import io
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("META-INF/mods.toml", EMPTY_FORGE_TOML)
        zf.writestr("com/example/Clean.class", b"\xca\xfe\xba\xbejava/lang/String")
    server_jar_bytes = buf.getvalue()

    entries = [
        {
            "path": "mods/entityculling.jar",
            "env": {"server": "required", "client": "required"},
            "downloads": ["https://stub.invalid/entityculling.jar"],
            "hashes": {},
        },
        {
            "path": "mods/uncertain-server.jar",
            "env": {"server": "required", "client": "required"},
            "downloads": ["https://stub.invalid/uncertain.jar"],
            "hashes": {},
        },
    ]
    _stub_download_with_payloads(monkeypatch, {
        "https://stub.invalid/entityculling.jar": client_jar_bytes,
        "https://stub.invalid/uncertain.jar": server_jar_bytes,
    })

    result = mod_client._install_index_files(
        entries, install_path, overrides={}, allow_missing=False, loader="forge",
    )

    assert result["files_installed"] == ["mods/uncertain-server.jar"]
    assert result["files_skipped"] == ["mods/entityculling.jar"]
    assert result["uncertain_mod_files"] == []
    assert not (install_path / "mods" / "entityculling.jar").exists()
    assert (install_path / "mods" / "uncertain-server.jar").is_file()


def test_install_e2e_classifier_catches_lwjgl_mod(mod_client, tmp_path, monkeypatch):
    """Forge jar with empty mods.toml + an LWJGL class ref must be skipped.

    Metadata reader returns uncertain, the constant-pool scan promotes it
    to ``client``, and ``_install_index_files`` records the skip + unlinks
    the freshly downloaded jar.
    """
    install_path = tmp_path / "server"
    install_path.mkdir()

    import io
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("META-INF/mods.toml", EMPTY_FORGE_TOML)
        zf.writestr(
            "com/example/Renderer.class",
            b"\xca\xfe\xba\xbeorg/lwjgl/glfw/GLFWErrorCallbackI",
        )
    lwjgl_jar_bytes = buf.getvalue()

    entries = [
        {
            "path": "mods/lwjgl-mod.jar",
            "env": {"server": "required", "client": "required"},
            "downloads": ["https://stub.invalid/lwjgl.jar"],
            "hashes": {},
        },
    ]
    _stub_download_with_payloads(monkeypatch, {
        "https://stub.invalid/lwjgl.jar": lwjgl_jar_bytes,
    })

    result = mod_client._install_index_files(
        entries, install_path, overrides={}, allow_missing=False, loader="forge",
    )

    assert result["files_installed"] == []
    assert result["files_skipped"] == ["mods/lwjgl-mod.jar"]
    assert result["uncertain_mod_files"] == []
    assert not (install_path / "mods" / "lwjgl-mod.jar").exists()
