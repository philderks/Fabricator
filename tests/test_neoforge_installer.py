"""NeoForgeInstaller — Maven-backed installer with subprocess install step."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def fake_maven_versions():
    """A representative slice of the real Maven response."""
    return {
        "isSnapshot": False,
        "versions": [
            "20.2.86",
            "20.2.88",
            "20.4.237",
            "21.0.143",
            "21.0.142-beta",
            "21.1.7",
            "21.1.228",
            "21.4.157",
            "21.11.42",
            "26.1.2.43-beta",
        ],
    }


def _patch_session(installer, *, maven_response=None, installer_jar_bytes=b"PKneoforgeINST"):
    """Stub installer.session.get to return canned responses."""
    session = MagicMock()

    def get(url, **_):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.headers = {"Content-Length": str(len(installer_jar_bytes))}
        if "api/maven/versions/releases" in url:
            resp.json.return_value = maven_response
        elif url.endswith(".jar"):
            resp.iter_content = lambda chunk_size=8192: iter([installer_jar_bytes])
            resp.__enter__ = lambda s: s
            resp.__exit__ = lambda *a: False
        elif url.endswith(".sha1"):
            import hashlib
            resp.text = hashlib.sha1(installer_jar_bytes).hexdigest()
        return resp

    session.get.side_effect = get
    installer.session = session
    return session


def test_loader_name(tmp_path):
    from backend.server.installer.neoforge import NeoForgeInstaller
    assert NeoForgeInstaller(tmp_path).loader_name == "neoforge"


def test_requires_java_for_install_is_true(tmp_path):
    from backend.server.installer.neoforge import NeoForgeInstaller
    assert NeoForgeInstaller(tmp_path).requires_java_for_install is True


def test_get_minecraft_versions_filters_and_normalizes(tmp_path, fake_maven_versions):
    from backend.server.installer.neoforge import NeoForgeInstaller
    inst = NeoForgeInstaller(tmp_path)
    _patch_session(inst, maven_response=fake_maven_versions)

    versions = inst.get_minecraft_versions()

    mc_strings = [v["version"] for v in versions]
    # 20.2.86 and 20.2.88 → 1.20.2 (stable, present)
    assert "1.20.2" in mc_strings
    # 20.4.237 → 1.20.4
    assert "1.20.4" in mc_strings
    # 21.0.143 stable + 21.0.142-beta → 1.21.0 (stable=True, since at least one stable)
    assert "1.21.0" in mc_strings
    # 21.1.x → 1.21.1
    assert "1.21.1" in mc_strings
    # 26.1.2.43-beta → 26.1.2 (year-versioned, stable=False since only beta)
    assert "26.1.2" in mc_strings

    for entry in versions:
        assert set(entry.keys()) >= {"version", "stable", "type"}
        assert isinstance(entry["stable"], bool)


def test_get_minecraft_versions_excludes_pre_1_20_2(tmp_path):
    from backend.server.installer.neoforge import NeoForgeInstaller
    inst = NeoForgeInstaller(tmp_path)
    _patch_session(inst, maven_response={
        "isSnapshot": False,
        "versions": ["20.1.5", "20.0.99", "21.1.228"],
    })

    versions = inst.get_minecraft_versions()
    mcs = [v["version"] for v in versions]
    assert "1.20.0" not in mcs
    assert "1.20.1" not in mcs
    assert "1.21.1" in mcs


def test_get_available_versions_filters_to_mc(tmp_path, fake_maven_versions):
    from backend.server.installer.neoforge import NeoForgeInstaller
    inst = NeoForgeInstaller(tmp_path)
    _patch_session(inst, maven_response=fake_maven_versions)

    versions_for_1_21_1 = inst.get_available_versions("1.21.1")
    raw = [v["version"] for v in versions_for_1_21_1]
    assert "21.1.7" in raw
    assert "21.1.228" in raw
    assert all(v.startswith("21.1.") for v in raw)

    versions_for_26_1_2 = inst.get_available_versions("26.1.2")
    raw26 = [v["version"] for v in versions_for_26_1_2]
    assert raw26 == ["26.1.2.43-beta"]


def test_get_available_versions_unknown_mc_returns_empty(tmp_path, fake_maven_versions):
    from backend.server.installer.neoforge import NeoForgeInstaller
    inst = NeoForgeInstaller(tmp_path)
    _patch_session(inst, maven_response=fake_maven_versions)

    assert inst.get_available_versions("1.19.4") == []
    assert inst.get_available_versions(None) == []
