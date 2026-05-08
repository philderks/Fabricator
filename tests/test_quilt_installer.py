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


def test_install_resolves_installer_version_from_maven_metadata(
    tmp_path, fake_game_versions, monkeypatch
):
    """install() picks the <release> version from quilt-installer's maven-metadata.xml."""
    import subprocess
    from backend.server.installer.quilt import QuiltInstaller
    inst = QuiltInstaller(tmp_path)
    _patch_session(inst, game_versions=fake_game_versions, maven_metadata_release="0.12.1")

    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["cwd"] = kwargs.get("cwd")
        # Simulate the installer's output: drop a quilt-server-launch.jar.
        (tmp_path / "quilt-server-launch.jar").write_bytes(b"PKquilt-launch")
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr("backend.server.installer.quilt.subprocess.run", fake_run)

    result = inst.install("1.21.4")

    assert result.success is True
    # Maven path includes the resolved installer version.
    jar_arg_index = captured["cmd"].index("-jar") + 1
    installer_path = captured["cmd"][jar_arg_index]
    assert "quilt-installer-0.12.1.jar" in installer_path
    # Install command form per Quilt docs: install server <mc> --download-server.
    assert captured["cmd"][jar_arg_index + 1:] == [
        "install", "server", "1.21.4", "--download-server"
    ]
    assert str(captured["cwd"]) == str(tmp_path)


def test_install_returns_jar_launchspec(tmp_path, fake_game_versions, monkeypatch):
    import subprocess
    from backend.server.installer.quilt import QuiltInstaller
    inst = QuiltInstaller(tmp_path)
    _patch_session(inst, game_versions=fake_game_versions)

    def fake_run(cmd, **kwargs):
        (tmp_path / "quilt-server-launch.jar").write_bytes(b"PKquilt")
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")
    monkeypatch.setattr("backend.server.installer.quilt.subprocess.run", fake_run)

    result = inst.install("1.21.4")
    assert result.success is True
    assert result.launch is not None
    assert result.launch.type == "jar"
    assert result.launch.jar == "quilt-server-launch.jar"
    assert result.launch.program_args == ["nogui"]
    assert result.launch.jvm_args == []
    assert result.launch.args_file is None
    # EULA written.
    assert (tmp_path / "eula.txt").read_text().strip() == "eula=true"


def test_install_uses_set_java_exec_path_for_subprocess(
    tmp_path, fake_game_versions, monkeypatch
):
    """When set_java_exec was called, the subprocess invokes that exact path."""
    import subprocess
    from backend.server.installer.quilt import QuiltInstaller
    inst = QuiltInstaller(tmp_path)
    _patch_session(inst, game_versions=fake_game_versions)
    inst.set_java_exec("/var/lib/fabricator/java/jdk-21/bin/java")

    captured = {}
    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        (tmp_path / "quilt-server-launch.jar").write_bytes(b"PKquilt")
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")
    monkeypatch.setattr("backend.server.installer.quilt.subprocess.run", fake_run)

    result = inst.install("1.21.4")
    assert result.success is True
    assert captured["cmd"][0] == "/var/lib/fabricator/java/jdk-21/bin/java"


def test_install_subprocess_uses_no_window_kwargs(
    tmp_path, fake_game_versions, monkeypatch
):
    """Match the codebase convention from manager/java_manager/neoforge."""
    import subprocess
    from backend.server.installer.quilt import QuiltInstaller
    inst = QuiltInstaller(tmp_path)
    _patch_session(inst, game_versions=fake_game_versions)

    captured_kwargs = {}
    def fake_run(cmd, **kwargs):
        captured_kwargs.update(kwargs)
        (tmp_path / "quilt-server-launch.jar").write_bytes(b"PKquilt")
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    SENTINEL_KW = {"creationflags": 0x08000000}
    monkeypatch.setattr(
        "backend.server.installer.quilt.platform_utils.subprocess_no_window_kwargs",
        lambda: SENTINEL_KW,
    )
    monkeypatch.setattr("backend.server.installer.quilt.subprocess.run", fake_run)

    result = inst.install("1.21.4")
    assert result.success is True
    assert captured_kwargs.get("creationflags") == 0x08000000


def test_install_subprocess_failure_returns_failure(
    tmp_path, fake_game_versions, monkeypatch
):
    import subprocess
    from backend.server.installer.quilt import QuiltInstaller
    inst = QuiltInstaller(tmp_path)
    _patch_session(inst, game_versions=fake_game_versions)

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(args=cmd, returncode=2, stdout="", stderr="installer exploded")
    monkeypatch.setattr("backend.server.installer.quilt.subprocess.run", fake_run)

    result = inst.install("1.21.4")
    assert result.success is False
    assert "installer exploded" in result.message or "returncode 2" in result.message


def test_install_launcher_jar_missing_returns_failure(
    tmp_path, fake_game_versions, monkeypatch
):
    """If the installer succeeds but quilt-server-launch.jar isn't there, fail loudly."""
    import subprocess
    from backend.server.installer.quilt import QuiltInstaller
    inst = QuiltInstaller(tmp_path)
    _patch_session(inst, game_versions=fake_game_versions)

    def fake_run(cmd, **kwargs):
        # Don't create the launcher jar — simulate a malformed install.
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")
    monkeypatch.setattr("backend.server.installer.quilt.subprocess.run", fake_run)

    result = inst.install("1.21.4")
    assert result.success is False
    assert "quilt-server-launch.jar" in result.message


def test_install_sha1_mismatch_fails(tmp_path, fake_game_versions, monkeypatch):
    """SHA1 mismatch on the installer JAR aborts the install before subprocess runs."""
    import subprocess
    from backend.server.installer.quilt import QuiltInstaller
    inst = QuiltInstaller(tmp_path)

    bytes_payload = b"PKquiltINST"
    session = MagicMock()

    def get(url, **_):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.headers = {"Content-Length": str(len(bytes_payload))}
        if "/v3/versions/game" in url:
            resp.json.return_value = fake_game_versions
        elif url.endswith("maven-metadata.xml"):
            resp.text = "<metadata><versioning><release>0.12.1</release></versioning></metadata>"
        elif url.endswith(".jar"):
            resp.iter_content = lambda chunk_size=8192: iter([bytes_payload])
            resp.__enter__ = lambda s: s
            resp.__exit__ = lambda *a: False
        elif url.endswith(".sha1"):
            resp.text = "deadbeef" * 5  # 40 chars, intentionally wrong
        return resp

    session.get.side_effect = get
    inst.session = session

    subprocess_called = {"hit": False}
    def fake_run(*a, **k):
        subprocess_called["hit"] = True
        return subprocess.CompletedProcess(args=[], returncode=0)
    monkeypatch.setattr("backend.server.installer.quilt.subprocess.run", fake_run)

    result = inst.install("1.21.4")
    assert result.success is False
    assert "sha1" in result.message.lower()
    assert subprocess_called["hit"] is False  # never reached subprocess


def test_install_unknown_installer_version_falls_back(
    tmp_path, fake_game_versions, monkeypatch
):
    """If maven-metadata.xml is unfetchable, fail clean (no hardcoded fallback)."""
    import requests
    from backend.server.installer.quilt import QuiltInstaller
    inst = QuiltInstaller(tmp_path)

    session = MagicMock()

    def get(url, **_):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        if "/v3/versions/game" in url:
            resp.json.return_value = fake_game_versions
            return resp
        if url.endswith("maven-metadata.xml"):
            raise requests.RequestException("network down")
        return resp

    session.get.side_effect = get
    inst.session = session

    result = inst.install("1.21.4")
    assert result.success is False
    assert "installer" in result.message.lower()
