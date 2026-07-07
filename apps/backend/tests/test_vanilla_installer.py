"""VanillaInstaller — Mojang piston-meta-backed installer."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def fake_manifest():
    return {
        "latest": {"release": "1.21.4", "snapshot": "24w45a"},
        "versions": [
            {
                "id": "1.21.4",
                "type": "release",
                "url": "https://example.invalid/1.21.4.json",
            },
            {
                "id": "24w45a",
                "type": "snapshot",
                "url": "https://example.invalid/24w45a.json",
            },
        ],
    }


def _patch_session(installer, manifest=None, version_meta=None, jar_bytes=b"PK\x03\x04"):
    """Replace installer.session.get with a MagicMock returning fakes."""
    session = MagicMock()

    def get(url, **_):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.headers = {"Content-Length": str(len(jar_bytes)), "Content-Type": "application/octet-stream"}
        if "version_manifest" in url:
            resp.json.return_value = manifest
        elif "1.21.4.json" in url or "24w45a.json" in url:
            resp.json.return_value = version_meta
        elif "server.jar" in url or url.endswith(".jar"):
            resp.iter_content = lambda chunk_size=8192: iter([jar_bytes])
            resp.__enter__ = lambda s: s
            resp.__exit__ = lambda *a: False
        return resp

    session.get.side_effect = get
    installer.session = session
    return session


def test_loader_name(tmp_path):
    from backend.server.installer.vanilla import VanillaInstaller
    assert VanillaInstaller(tmp_path).loader_name == "vanilla"


def test_get_minecraft_versions_normalizes(tmp_path, fake_manifest):
    from backend.server.installer.vanilla import VanillaInstaller
    inst = VanillaInstaller(tmp_path)
    _patch_session(inst, manifest=fake_manifest)

    versions = inst.get_minecraft_versions()
    assert versions == [
        {"version": "1.21.4", "stable": True,  "type": "release"},
        {"version": "24w45a", "stable": False, "type": "snapshot"},
    ]


def test_get_available_versions_returns_empty(tmp_path):
    """Vanilla has no separate loader versions."""
    from backend.server.installer.vanilla import VanillaInstaller
    inst = VanillaInstaller(tmp_path)
    assert inst.get_available_versions("1.21.4") == []
    assert inst.get_available_versions(None) == []


def test_install_unknown_version_fails(tmp_path, fake_manifest):
    from backend.server.installer.vanilla import VanillaInstaller
    inst = VanillaInstaller(tmp_path)
    _patch_session(inst, manifest=fake_manifest)

    result = inst.install("9.9.9")
    assert result.success is False
    assert "9.9.9" in result.message


def test_install_success_writes_jar_and_eula_and_launch(tmp_path, fake_manifest):
    import hashlib
    from backend.server.installer.vanilla import VanillaInstaller
    inst = VanillaInstaller(tmp_path)
    jar_bytes = b"PK\x03\x04"
    expected_sha1 = hashlib.sha1(jar_bytes).hexdigest()
    version_meta = {
        "downloads": {
            "server": {
                "url": "https://example.invalid/server.jar",
                "sha1": expected_sha1,
                "size": len(jar_bytes),
            }
        }
    }
    _patch_session(inst, manifest=fake_manifest, version_meta=version_meta, jar_bytes=jar_bytes)

    result = inst.install("1.21.4")

    assert result.success is True
    assert (tmp_path / "server.jar").exists()
    assert (tmp_path / "eula.txt").read_text().strip() == "eula=true"
    assert result.launch is not None
    assert result.launch.type == "jar"
    assert result.launch.jar == "server.jar"
    assert result.launch.program_args == ["nogui"]


def test_install_skips_version_without_server_download(tmp_path, fake_manifest):
    """Some old versions have no downloads.server entry → install must fail cleanly."""
    from backend.server.installer.vanilla import VanillaInstaller
    inst = VanillaInstaller(tmp_path)
    _patch_session(inst, manifest=fake_manifest, version_meta={"downloads": {}})

    result = inst.install("1.21.4")
    assert result.success is False
    assert "no server download" in result.message.lower()


def test_install_fails_on_sha1_mismatch(tmp_path, fake_manifest):
    """SHA1 from piston-meta must match the downloaded bytes; mismatch aborts."""
    from backend.server.installer.vanilla import VanillaInstaller
    inst = VanillaInstaller(tmp_path)
    version_meta = {
        "downloads": {
            "server": {
                "url": "https://example.invalid/server.jar",
                "sha1": "deadbeef" * 5,  # 40 hex chars, intentionally wrong
                "size": 4,
            }
        }
    }
    _patch_session(inst, manifest=fake_manifest, version_meta=version_meta, jar_bytes=b"PK\x03\x04")

    result = inst.install("1.21.4")
    assert result.success is False
    assert "sha1" in result.message.lower()
    # Bad jar must not be left behind on disk.
    assert not (tmp_path / "server.jar").exists()
