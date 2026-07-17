"""PufferfishInstaller — Jenkins CI-backed (fragile, no upstream hash)."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest


JAR_BYTES = b"PK\x03\x04puffer"


def _patch_session(installer, *, jobs, artifacts, jar_bytes=JAR_BYTES):
    session = MagicMock()

    def get(url, **_):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.headers = {"Content-Length": str(len(jar_bytes))}
        if "/artifact/" in url:
            resp.iter_content = lambda chunk_size=8192: iter([jar_bytes])
            resp.__enter__ = lambda s: s
            resp.__exit__ = lambda *a: False
        elif "/lastSuccessfulBuild/api/json" in url:
            resp.json.return_value = {"artifacts": artifacts}
        else:  # /api/json?tree=jobs[name]
            resp.json.return_value = {"jobs": jobs}
        return resp

    session.get.side_effect = get
    installer.session = session
    return session


def test_loader_name_kind_facets(tmp_path):
    from backend.server.installer.pufferfish import PufferfishInstaller
    inst = PufferfishInstaller(tmp_path)
    assert inst.loader_name == "pufferfish"
    assert inst.content_kind == "plugin"
    assert inst.modrinth_loader_facets == ["paper", "spigot", "bukkit"]


def test_get_minecraft_versions_sorted_newest_first(tmp_path):
    from backend.server.installer.pufferfish import PufferfishInstaller
    inst = PufferfishInstaller(tmp_path)
    _patch_session(
        inst,
        jobs=[
            {"name": "Pufferfish-1.19"},
            {"name": "Pufferfish-1.21"},
            {"name": "Pufferfish-1.20"},
            {"name": "Pufferfish-Purpur-1.17"},  # variant — must be excluded
            {"name": "SomethingElse"},           # ignored
        ],
        artifacts=[],
    )
    versions = [v["version"] for v in inst.get_minecraft_versions()]
    assert versions == ["1.21", "1.20", "1.19"]


def test_install_success(tmp_path):
    from backend.server.installer.pufferfish import PufferfishInstaller
    inst = PufferfishInstaller(tmp_path)
    _patch_session(
        inst,
        jobs=[{"name": "Pufferfish-1.21"}],
        artifacts=[
            {"fileName": "pufferfish-paperclip-1.21-R0.1-SNAPSHOT-sources.jar",
             "relativePath": "pufferfish-server/build/libs/pufferfish-1.21-sources.jar"},
            {"fileName": "pufferfish-paperclip-1.21.10-R0.1-SNAPSHOT-mojmap.jar",
             "relativePath": "pufferfish-server/build/libs/pufferfish-paperclip-1.21.10-R0.1-SNAPSHOT-mojmap.jar"},
        ],
    )
    result = inst.install("1.21")
    assert result.success is True
    assert (tmp_path / "server.jar").exists()
    assert result.launch.jar == "server.jar"
    # -sources artefact must be skipped in favour of the real (nested) server jar.
    assert result.details["artifact"] == (
        "pufferfish-server/build/libs/pufferfish-paperclip-1.21.10-R0.1-SNAPSHOT-mojmap.jar"
    )


def test_resolve_artifact_prefers_paperclip(tmp_path):
    """When multiple runnable jars exist, the paperclip bootstrap jar wins."""
    from backend.server.installer.pufferfish import PufferfishInstaller
    inst = PufferfishInstaller(tmp_path)
    _patch_session(
        inst,
        jobs=[{"name": "Pufferfish-1.21"}],
        artifacts=[
            {"fileName": "pufferfish-bundler-1.21.jar",
             "relativePath": "pufferfish-server/build/libs/pufferfish-bundler-1.21.jar"},
            {"fileName": "pufferfish-paperclip-1.21-mojmap.jar",
             "relativePath": "pufferfish-server/build/libs/pufferfish-paperclip-1.21-mojmap.jar"},
        ],
    )
    assert inst._resolve_artifact_path("Pufferfish-1.21") == (
        "pufferfish-server/build/libs/pufferfish-paperclip-1.21-mojmap.jar"
    )


def test_install_missing_job_fails(tmp_path):
    from backend.server.installer.pufferfish import PufferfishInstaller
    inst = PufferfishInstaller(tmp_path)
    _patch_session(inst, jobs=[{"name": "Pufferfish-1.20"}], artifacts=[])
    result = inst.install("1.21")
    assert result.success is False
    assert "1.21" in result.message


def test_install_missing_artifact_fails(tmp_path):
    from backend.server.installer.pufferfish import PufferfishInstaller
    inst = PufferfishInstaller(tmp_path)
    _patch_session(
        inst,
        jobs=[{"name": "Pufferfish-1.21"}],
        artifacts=[{"fileName": "notes.txt", "relativePath": "build/libs/notes.txt"}],
    )
    result = inst.install("1.21")
    assert result.success is False
    assert "layout" in result.message.lower() or "build/libs" in result.message.lower()
