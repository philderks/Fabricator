"""PurpurInstaller — api.purpurmc.org v2-backed (no upstream hash gate)."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest


JAR_BYTES = b"PK\x03\x04purpur"


def _patch_session(installer, *, versions, builds, jar_bytes=JAR_BYTES):
    session = MagicMock()

    def get(url, **_):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.headers = {"Content-Length": str(len(jar_bytes))}
        if url.endswith("/download"):
            resp.iter_content = lambda chunk_size=8192: iter([jar_bytes])
            resp.__enter__ = lambda s: s
            resp.__exit__ = lambda *a: False
        elif url.rstrip("/").endswith("/purpur"):
            resp.json.return_value = {"versions": versions}
        else:  # /purpur/<mc>
            resp.json.return_value = {"builds": builds}
        return resp

    session.get.side_effect = get
    installer.session = session
    return session


def test_loader_name_kind_facets(tmp_path):
    from backend.server.installer.purpur import PurpurInstaller
    inst = PurpurInstaller(tmp_path)
    assert inst.loader_name == "purpur"
    assert inst.content_kind == "plugin"
    assert inst.modrinth_loader_facets == ["purpur", "paper", "spigot", "bukkit"]


def test_get_minecraft_versions_newest_first(tmp_path):
    from backend.server.installer.purpur import PurpurInstaller
    inst = PurpurInstaller(tmp_path)
    _patch_session(inst, versions=["1.20.6", "1.21", "1.21.4"], builds={})
    versions = inst.get_minecraft_versions()
    assert [v["version"] for v in versions] == ["1.21.4", "1.21", "1.20.6"]


def test_install_success(tmp_path):
    from backend.server.installer.purpur import PurpurInstaller
    inst = PurpurInstaller(tmp_path)
    _patch_session(
        inst,
        versions=["1.21.4"],
        builds={"latest": "2296", "all": ["2295", "2296"]},
    )
    result = inst.install("1.21.4")
    assert result.success is True
    assert (tmp_path / "server.jar").exists()
    assert (tmp_path / "eula.txt").read_text().strip() == "eula=true"
    assert result.launch.jar == "server.jar"
    assert result.details["build"] == "2296"


def test_install_no_build_fails(tmp_path):
    from backend.server.installer.purpur import PurpurInstaller
    inst = PurpurInstaller(tmp_path)
    _patch_session(inst, versions=["1.21.4"], builds={})
    result = inst.install("1.21.4")
    assert result.success is False
    assert "1.21.4" in result.message
