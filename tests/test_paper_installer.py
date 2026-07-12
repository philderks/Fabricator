"""PaperMC-family installers (Paper, Folia) — fill.papermc.io v3-backed."""
from __future__ import annotations

import hashlib
from unittest.mock import MagicMock

import pytest


JAR_BYTES = b"PK\x03\x04paper"


def _patch_session(installer, *, versions_map, builds, jar_bytes=JAR_BYTES):
    """Mock installer.session.get for the PaperMC Fill v3 endpoints."""
    session = MagicMock()

    def get(url, **_):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.headers = {"Content-Length": str(len(jar_bytes))}
        if "/jar/" in url:  # a build download URL
            resp.iter_content = lambda chunk_size=8192: iter([jar_bytes])
            resp.__enter__ = lambda s: s
            resp.__exit__ = lambda *a: False
        elif "/builds" in url:
            resp.json.return_value = builds
        else:  # /projects/<project>
            resp.json.return_value = {"versions": versions_map}
        return resp

    session.get.side_effect = get
    installer.session = session
    return session


def _build_entry(build_id, sha256, *, channel="STABLE", name="paper-1.21.4-42.jar"):
    return {
        "id": build_id,
        "channel": channel,
        "downloads": {
            "server:default": {
                "name": name,
                "url": f"https://example.invalid/jar/{name}",
                "checksums": {"sha256": sha256},
            }
        },
    }


def test_loader_name_and_content_kind(tmp_path):
    from backend.server.installer.papermc import PaperInstaller, FoliaInstaller
    assert PaperInstaller(tmp_path).loader_name == "paper"
    assert FoliaInstaller(tmp_path).loader_name == "folia"
    assert PaperInstaller(tmp_path).content_kind == "plugin"
    assert FoliaInstaller(tmp_path).content_kind == "plugin"


def test_modrinth_facets(tmp_path):
    from backend.server.installer.papermc import PaperInstaller, FoliaInstaller
    assert PaperInstaller(tmp_path).modrinth_loader_facets == ["paper", "spigot", "bukkit"]
    # Folia stays strict — it must not silently accept generic Paper plugins.
    assert FoliaInstaller(tmp_path).modrinth_loader_facets == ["folia"]


def test_get_minecraft_versions_newest_first_and_stability(tmp_path):
    from backend.server.installer.papermc import PaperInstaller
    inst = PaperInstaller(tmp_path)
    # Fill v3 groups by family (newest family first, newest version first).
    _patch_session(
        inst,
        versions_map={
            "1.21": ["1.21.4", "1.21.4-rc1", "1.21"],
            "1.20": ["1.20.6"],
        },
        builds=[],
    )
    versions = inst.get_minecraft_versions()
    assert [v["version"] for v in versions] == ["1.21.4", "1.21.4-rc1", "1.21", "1.20.6"]
    stability = {v["version"]: v["stable"] for v in versions}
    assert stability["1.21.4"] is True
    assert stability["1.21.4-rc1"] is False  # prerelease marked non-stable


def test_get_minecraft_versions_sorts_shuffled_input(tmp_path):
    """Ordering must not depend on the API's list order."""
    from backend.server.installer.papermc import PaperInstaller
    inst = PaperInstaller(tmp_path)
    _patch_session(
        inst,
        versions_map={
            "1.20": ["1.20.1", "1.20.6"],       # out of order within family
            "1.21": ["1.21", "1.21.10", "1.21.4"],
        },
        builds=[],
    )
    versions = [v["version"] for v in inst.get_minecraft_versions()]
    assert versions == ["1.21.10", "1.21.4", "1.21", "1.20.6", "1.20.1"]


def test_install_success_writes_jar_eula_launch(tmp_path):
    from backend.server.installer.papermc import PaperInstaller
    inst = PaperInstaller(tmp_path)
    sha256 = hashlib.sha256(JAR_BYTES).hexdigest()
    builds = [
        _build_entry(40, "0" * 64, channel="ALPHA"),
        _build_entry(42, sha256, channel="STABLE"),
    ]
    _patch_session(inst, versions_map={"1.21": ["1.21.4"]}, builds=builds)

    result = inst.install("1.21.4")
    assert result.success is True
    assert (tmp_path / "server.jar").exists()
    assert (tmp_path / "eula.txt").read_text().strip() == "eula=true"
    assert result.launch.type == "jar"
    assert result.launch.jar == "server.jar"
    assert result.launch.program_args == ["nogui"]
    assert result.details["build"] == 42  # newest STABLE build wins


def test_install_fails_on_sha256_mismatch(tmp_path):
    from backend.server.installer.papermc import PaperInstaller
    inst = PaperInstaller(tmp_path)
    builds = [_build_entry(42, "deadbeef" * 8)]  # 64 hex, wrong
    _patch_session(inst, versions_map={"1.21": ["1.21.4"]}, builds=builds)

    result = inst.install("1.21.4")
    assert result.success is False
    assert "sha256" in result.message.lower()
    assert not (tmp_path / "server.jar").exists()


def test_install_no_build_fails_cleanly(tmp_path):
    from backend.server.installer.papermc import PaperInstaller
    inst = PaperInstaller(tmp_path)
    _patch_session(inst, versions_map={"1.21": ["1.21.4"]}, builds=[])
    result = inst.install("1.21.4")
    assert result.success is False
    assert "1.21.4" in result.message


def test_folia_uses_folia_project(tmp_path):
    from backend.server.installer.papermc import FoliaInstaller
    inst = FoliaInstaller(tmp_path)
    session = _patch_session(inst, versions_map={"1.21": ["1.21.4"]}, builds=[])
    inst.get_minecraft_versions()
    called_urls = [c.args[0] for c in session.get.call_args_list]
    assert any("/projects/folia" in u for u in called_urls)
