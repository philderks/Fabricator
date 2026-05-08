"""QuiltInstaller — Quilt Meta + Maven-backed installer with subprocess install step."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def fake_game_versions():
    """A representative slice of the Quilt /v3/versions/game response."""
    return [
        {"version": "1.21.4", "stable": True},
        {"version": "1.21.3", "stable": True},
        {"version": "25w03a", "stable": False},
        {"version": "1.21.1", "stable": True},
    ]


@pytest.fixture
def fake_loader_versions():
    """A representative slice of /v3/versions/loader/1.21.4 (nested shape)."""
    return [
        {
            "loader": {
                "maven": "org.quiltmc:quilt-loader:0.27.0",
                "version": "0.27.0",
                "build": 0,
            },
            "hashed": {"version": "1.21.4"},
            "intermediary": {"version": "1.21.4"},
            "launcherMeta": {"version": 2, "min_java_version": 8},
        },
        {
            "loader": {
                "maven": "org.quiltmc:quilt-loader:0.26.4",
                "version": "0.26.4",
                "build": 0,
            },
            "hashed": {"version": "1.21.4"},
            "intermediary": {"version": "1.21.4"},
            "launcherMeta": {"version": 2, "min_java_version": 8},
        },
    ]


def _patch_session(installer, *, game_versions=None, loader_versions=None,
                   maven_metadata_release="0.12.1",
                   installer_jar_bytes=b"PKquiltINST"):
    """Stub installer.session.get to return canned responses."""
    session = MagicMock()

    def get(url, **_):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.headers = {"Content-Length": str(len(installer_jar_bytes))}
        if "/v3/versions/game" in url:
            resp.json.return_value = game_versions
        elif "/v3/versions/loader/" in url:
            resp.json.return_value = loader_versions
        elif url.endswith("maven-metadata.xml"):
            resp.text = (
                "<metadata><versioning>"
                f"<release>{maven_metadata_release}</release>"
                "</versioning></metadata>"
            )
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
    from backend.server.installer.quilt import QuiltInstaller
    assert QuiltInstaller(tmp_path).loader_name == "quilt"


def test_requires_java_for_install_is_true(tmp_path):
    from backend.server.installer.quilt import QuiltInstaller
    assert QuiltInstaller(tmp_path).requires_java_for_install is True


def test_get_minecraft_versions_normalizes(tmp_path, fake_game_versions):
    from backend.server.installer.quilt import QuiltInstaller
    inst = QuiltInstaller(tmp_path)
    _patch_session(inst, game_versions=fake_game_versions)

    versions = inst.get_minecraft_versions()

    # All four fixture entries surface, each gains a "type" field.
    assert len(versions) == 4
    by_version = {v["version"]: v for v in versions}
    assert by_version["1.21.4"]["stable"] is True
    assert by_version["1.21.4"]["type"] == "release"
    assert by_version["25w03a"]["stable"] is False
    assert by_version["25w03a"]["type"] == "snapshot"


def test_get_minecraft_versions_returns_empty_on_meta_failure(tmp_path):
    """A network error on Meta must produce a clean empty list, not an exception."""
    import requests
    from backend.server.installer.quilt import QuiltInstaller
    inst = QuiltInstaller(tmp_path)
    session = MagicMock()
    session.get.side_effect = requests.RequestException("boom")
    inst.session = session

    assert inst.get_minecraft_versions() == []


def test_get_available_versions_flattens_loader_entries(tmp_path, fake_loader_versions):
    from backend.server.installer.quilt import QuiltInstaller
    inst = QuiltInstaller(tmp_path)
    _patch_session(inst, loader_versions=fake_loader_versions)

    versions = inst.get_available_versions("1.21.4")
    raw = [v["version"] for v in versions]
    assert raw == ["0.27.0", "0.26.4"]
    assert all(v["stable"] is True for v in versions)
    assert all(v["type"] == "release" for v in versions)


def test_get_available_versions_unknown_mc_returns_empty(tmp_path):
    """Quilt Meta returns 404 for unsupported MC versions; we surface []."""
    import requests
    from backend.server.installer.quilt import QuiltInstaller
    inst = QuiltInstaller(tmp_path)
    session = MagicMock()
    session.get.side_effect = requests.RequestException("404")
    inst.session = session

    assert inst.get_available_versions("1.10.2") == []
    assert inst.get_available_versions(None) == []
