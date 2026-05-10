"""ForgeInstaller — Forge promotions-API + Maven-backed installer.

Phase 3b.1 T1 covers the version-listing layer; T2 fills in the install
body with era dispatch (legacy single-jar vs modern args_file).
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def fake_promotions():
    """A representative slice of the Forge promotions_slim.json response.

    Covers all four eras: 1.7.10 (legacy, both pointers identical),
    1.12.2 (legacy, recommended != latest), 1.16.5 (legacy/transition),
    1.20.1 (modern), 1.21.4 (modern, current). Plus 1.18.1 with ONLY
    a latest pointer (no recommended) — common edge case during a Forge
    transition window.
    """
    return {
        "homepage": "https://files.minecraftforge.net/...",
        "promos": {
            "1.7.10-latest": "10.13.4.1614",
            "1.7.10-recommended": "10.13.4.1614",
            "1.12.2-latest": "14.23.5.2864",
            "1.12.2-recommended": "14.23.5.2859",
            "1.16.5-latest": "36.2.42",
            "1.16.5-recommended": "36.2.34",
            "1.18.1-latest": "39.1.2",
            "1.20.1-latest": "47.4.20",
            "1.20.1-recommended": "47.4.10",
            "1.21.4-latest": "54.1.16",
            "1.21.4-recommended": "54.1.14",
        },
    }


def _patch_session(installer, *, promotions=None, raise_exc=None):
    """Stub installer.session.get to return canned promotions or raise."""
    session = MagicMock()

    def get(url, **_):
        if raise_exc is not None:
            raise raise_exc
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        if "promotions_slim.json" in url:
            resp.json.return_value = promotions
        return resp

    session.get.side_effect = get
    installer.session = session
    return session


def test_loader_name(tmp_path):
    from backend.server.installer.forge import ForgeInstaller
    assert ForgeInstaller(tmp_path).loader_name == "forge"


def test_requires_java_for_install_is_true(tmp_path):
    from backend.server.installer.forge import ForgeInstaller
    assert ForgeInstaller(tmp_path).requires_java_for_install is True


def test_get_minecraft_versions_dedups_and_sorts(tmp_path, fake_promotions):
    """Each MC version surfaces once, sorted descending (newest first)."""
    from backend.server.installer.forge import ForgeInstaller
    inst = ForgeInstaller(tmp_path)
    _patch_session(inst, promotions=fake_promotions)

    versions = inst.get_minecraft_versions()
    raw = [v["version"] for v in versions]

    # Each MC version appears once (no duplicates from -latest/-recommended).
    assert raw == [
        "1.21.4",
        "1.20.1",
        "1.18.1",
        "1.16.5",
        "1.12.2",
        "1.7.10",
    ]
    # All Forge releases are stable (no pre-release / snapshot concept here).
    assert all(v["stable"] is True for v in versions)
    assert all(v["type"] == "release" for v in versions)


def test_get_available_versions_prefers_recommended_then_latest(
    tmp_path, fake_promotions
):
    """When both pointers exist, return [recommended, latest] in that order."""
    from backend.server.installer.forge import ForgeInstaller
    inst = ForgeInstaller(tmp_path)
    _patch_session(inst, promotions=fake_promotions)

    versions = inst.get_available_versions("1.20.1")
    raw = [v["version"] for v in versions]
    # Recommended first (the "preferred" stable build), then latest.
    assert raw == ["47.4.10", "47.4.20"]
    assert all(v["stable"] is True for v in versions)


def test_get_available_versions_latest_only_when_no_recommended(
    tmp_path, fake_promotions
):
    """1.18.1 in the fixture has only -latest. Surface that one alone."""
    from backend.server.installer.forge import ForgeInstaller
    inst = ForgeInstaller(tmp_path)
    _patch_session(inst, promotions=fake_promotions)

    versions = inst.get_available_versions("1.18.1")
    raw = [v["version"] for v in versions]
    assert raw == ["39.1.2"]


def test_get_available_versions_unknown_mc_returns_empty(
    tmp_path, fake_promotions
):
    from backend.server.installer.forge import ForgeInstaller
    inst = ForgeInstaller(tmp_path)
    _patch_session(inst, promotions=fake_promotions)

    assert inst.get_available_versions("1.5.2") == []
    assert inst.get_available_versions(None) == []


def test_get_minecraft_versions_returns_empty_on_meta_failure(tmp_path):
    """Network error or malformed JSON → clean [], not an exception."""
    import requests
    from backend.server.installer.forge import ForgeInstaller
    inst = ForgeInstaller(tmp_path)
    _patch_session(inst, raise_exc=requests.RequestException("boom"))

    assert inst.get_minecraft_versions() == []


def _patch_session_with_install(installer, *, promotions=None,
                                installer_jar_bytes=b"PKforgeINST"):
    """Stub installer.session.get for promotions + Maven jar + sha1 endpoints."""
    session = MagicMock()

    def get(url, **_):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.headers = {"Content-Length": str(len(installer_jar_bytes))}
        if "promotions_slim.json" in url:
            resp.json.return_value = promotions
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


def test_install_legacy_1_16_5_returns_jar_launchspec(
    tmp_path, fake_promotions, monkeypatch
):
    """Legacy era: produces forge-<mc>-<build>.jar in install root."""
    import subprocess
    from backend.server.installer.forge import ForgeInstaller
    inst = ForgeInstaller(tmp_path)
    _patch_session_with_install(inst, promotions=fake_promotions)

    def fake_run(cmd, **kwargs):
        # Simulate Forge 1.16.5 installer output: launcher jar in cwd.
        # Build = recommended for 1.16.5 = 36.2.34
        (tmp_path / "forge-1.16.5-36.2.34.jar").write_bytes(b"PKforge-launcher")
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="ok", stderr="")
    monkeypatch.setattr("backend.server.installer.forge.run_subprocess_streaming", fake_run)

    result = inst.install("1.16.5")
    assert result.success is True
    assert result.launch is not None
    assert result.launch.type == "jar"
    assert result.launch.jar == "forge-1.16.5-36.2.34.jar"
    assert result.launch.args_file is None
    assert result.launch.program_args == ["nogui"]
    assert (tmp_path / "eula.txt").read_text().strip() == "eula=true"


def test_install_legacy_pre_1_13_returns_universal_jar_launchspec(
    tmp_path, monkeypatch
):
    """Pre-1.13 (≤1.12.2) legacy: launcher uses -universal.jar suffix."""
    import subprocess
    from backend.server.installer.forge import ForgeInstaller
    inst = ForgeInstaller(tmp_path)
    promotions = {
        "promos": {
            "1.12.2-recommended": "14.23.5.2859",
            "1.12.2-latest": "14.23.5.2864",
        }
    }
    _patch_session_with_install(inst, promotions=promotions)

    def fake_run(cmd, **kwargs):
        # 1.12.2 produces -universal.jar.
        (tmp_path / "forge-1.12.2-14.23.5.2859-universal.jar").write_bytes(b"PKuni")
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")
    monkeypatch.setattr("backend.server.installer.forge.run_subprocess_streaming", fake_run)

    result = inst.install("1.12.2")
    assert result.success is True
    assert result.launch.type == "jar"
    assert result.launch.jar == "forge-1.12.2-14.23.5.2859-universal.jar"


def test_install_modern_1_20_1_returns_args_file_launchspec(
    tmp_path, fake_promotions, monkeypatch
):
    """Modern era: produces libraries/.../unix_args.txt."""
    import subprocess
    from backend.server.installer.forge import ForgeInstaller
    inst = ForgeInstaller(tmp_path)
    _patch_session_with_install(inst, promotions=fake_promotions)

    def fake_run(cmd, **kwargs):
        # Build = recommended for 1.20.1 = 47.4.10
        target = (tmp_path / "libraries" / "net" / "minecraftforge"
                  / "forge" / "1.20.1-47.4.10")
        target.mkdir(parents=True, exist_ok=True)
        (target / "unix_args.txt").write_text("# args\n")
        (target / "win_args.txt").write_text("# args\n")
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")
    monkeypatch.setattr("backend.server.installer.forge.run_subprocess_streaming", fake_run)
    monkeypatch.setattr("backend.server.installer.forge.is_windows", lambda: False)

    result = inst.install("1.20.1")
    assert result.success is True
    assert result.launch.type == "args_file"
    assert result.launch.args_file == (
        "libraries/net/minecraftforge/forge/1.20.1-47.4.10/unix_args.txt"
    )
    assert result.launch.jar is None
    assert result.launch.program_args == ["nogui"]


def test_install_subprocess_command_includes_explicit_install_dir(
    tmp_path, fake_promotions, monkeypatch
):
    """The subprocess MUST pass --installServer <install_path> explicitly.

    Quilt commit 541f26a established this defensive pattern: relying on
    cwd alone is the bug-vector that broke Quilt installs. Forge supports
    --installServer <path> per the audit (verified empirically) so we use
    it. This test pins the cmd shape so a future refactor can't regress
    it back to the cwd-only form.
    """
    import subprocess
    from backend.server.installer.forge import ForgeInstaller
    inst = ForgeInstaller(tmp_path)
    _patch_session_with_install(inst, promotions=fake_promotions)

    captured = {}
    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["cwd"] = kwargs.get("cwd")
        # Simulate modern output for 1.20.1 (recommended=47.4.10).
        target = (tmp_path / "libraries" / "net" / "minecraftforge"
                  / "forge" / "1.20.1-47.4.10")
        target.mkdir(parents=True, exist_ok=True)
        (target / "unix_args.txt").write_text("# args\n")
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")
    monkeypatch.setattr("backend.server.installer.forge.run_subprocess_streaming", fake_run)
    monkeypatch.setattr("backend.server.installer.forge.is_windows", lambda: False)

    result = inst.install("1.20.1")
    assert result.success is True
    # cmd shape: [java, -jar, <installer>, --installServer, <install_path>]
    assert "--installServer" in captured["cmd"]
    install_dir_idx = captured["cmd"].index("--installServer") + 1
    assert captured["cmd"][install_dir_idx] == str(tmp_path)
    assert str(captured["cwd"]) == str(tmp_path)


def test_install_uses_set_java_exec_path_for_subprocess(
    tmp_path, fake_promotions, monkeypatch
):
    import subprocess
    from backend.server.installer.forge import ForgeInstaller
    inst = ForgeInstaller(tmp_path)
    _patch_session_with_install(inst, promotions=fake_promotions)
    inst.set_java_exec("/var/lib/fabricator/java/jdk-21/bin/java")

    captured = {}
    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        target = (tmp_path / "libraries" / "net" / "minecraftforge"
                  / "forge" / "1.20.1-47.4.10")
        target.mkdir(parents=True, exist_ok=True)
        (target / "unix_args.txt").write_text("# args\n")
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")
    monkeypatch.setattr("backend.server.installer.forge.run_subprocess_streaming", fake_run)
    monkeypatch.setattr("backend.server.installer.forge.is_windows", lambda: False)

    result = inst.install("1.20.1")
    assert result.success is True
    assert captured["cmd"][0] == "/var/lib/fabricator/java/jdk-21/bin/java"


def test_install_subprocess_uses_no_window_kwargs(
    tmp_path, fake_promotions, monkeypatch
):
    """Match codebase convention from manager / java_manager / neoforge / quilt."""
    import subprocess
    from backend.server.installer.forge import ForgeInstaller
    inst = ForgeInstaller(tmp_path)
    _patch_session_with_install(inst, promotions=fake_promotions)

    captured_kwargs = {}
    def fake_run(cmd, **kwargs):
        captured_kwargs.update(kwargs)
        target = (tmp_path / "libraries" / "net" / "minecraftforge"
                  / "forge" / "1.20.1-47.4.10")
        target.mkdir(parents=True, exist_ok=True)
        (target / "unix_args.txt").write_text("# args\n")
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    SENTINEL_KW = {"creationflags": 0x08000000}
    monkeypatch.setattr(
        "backend.server.installer.forge.platform_utils.subprocess_no_window_kwargs",
        lambda: SENTINEL_KW,
    )
    monkeypatch.setattr("backend.server.installer.forge.run_subprocess_streaming", fake_run)
    monkeypatch.setattr("backend.server.installer.forge.is_windows", lambda: False)

    result = inst.install("1.20.1")
    assert result.success is True
    assert captured_kwargs.get("creationflags") == 0x08000000


def test_install_subprocess_failure_returns_failure(
    tmp_path, fake_promotions, monkeypatch
):
    import subprocess
    from backend.server.installer.forge import ForgeInstaller
    inst = ForgeInstaller(tmp_path)
    _patch_session_with_install(inst, promotions=fake_promotions)

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(args=cmd, returncode=2, stdout="", stderr="installer exploded")
    monkeypatch.setattr("backend.server.installer.forge.run_subprocess_streaming", fake_run)

    result = inst.install("1.20.1")
    assert result.success is False
    assert "installer exploded" in result.message or "returncode 2" in result.message


def test_install_unexpected_layout_returns_failure(
    tmp_path, fake_promotions, monkeypatch
):
    """Subprocess succeeds but produces neither a launcher jar nor args files."""
    import subprocess
    from backend.server.installer.forge import ForgeInstaller
    inst = ForgeInstaller(tmp_path)
    _patch_session_with_install(inst, promotions=fake_promotions)

    def fake_run(cmd, **kwargs):
        # Don't create any launcher artefact — simulate a malformed install.
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")
    monkeypatch.setattr("backend.server.installer.forge.run_subprocess_streaming", fake_run)
    monkeypatch.setattr("backend.server.installer.forge.is_windows", lambda: False)

    result = inst.install("1.20.1")
    assert result.success is False
    msg = result.message.lower()
    assert "unexpected layout" in msg or "unexpected" in msg
    assert "args_file" in msg or "unix_args" in msg or "forge-" in msg


def test_install_modern_wins_when_both_artefacts_present(
    tmp_path, fake_promotions, monkeypatch
):
    """Defensive: if both modern args_file AND legacy jar exist, modern wins.

    Pins deterministic dispatch when an unusual installer build (or a
    re-install after era boundary) lays down both layouts.
    """
    import subprocess
    from backend.server.installer.forge import ForgeInstaller
    inst = ForgeInstaller(tmp_path)
    _patch_session_with_install(inst, promotions=fake_promotions)

    def fake_run(cmd, **kwargs):
        # Modern artefact:
        target = (tmp_path / "libraries" / "net" / "minecraftforge"
                  / "forge" / "1.20.1-47.4.10")
        target.mkdir(parents=True, exist_ok=True)
        (target / "unix_args.txt").write_text("# args\n")
        # Legacy artefact too (defensive corner case):
        (tmp_path / "forge-1.20.1-47.4.10.jar").write_bytes(b"PKlegacy")
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")
    monkeypatch.setattr("backend.server.installer.forge.run_subprocess_streaming", fake_run)
    monkeypatch.setattr("backend.server.installer.forge.is_windows", lambda: False)

    result = inst.install("1.20.1")
    assert result.success is True
    assert result.launch.type == "args_file"
    assert result.launch.jar is None


def test_install_modern_uses_windows_args_file_on_windows(
    tmp_path, fake_promotions, monkeypatch
):
    import subprocess
    from backend.server.installer.forge import ForgeInstaller
    inst = ForgeInstaller(tmp_path)
    _patch_session_with_install(inst, promotions=fake_promotions)

    def fake_run(cmd, **kwargs):
        target = (tmp_path / "libraries" / "net" / "minecraftforge"
                  / "forge" / "1.20.1-47.4.10")
        target.mkdir(parents=True, exist_ok=True)
        (target / "win_args.txt").write_text("# args\n")
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")
    monkeypatch.setattr("backend.server.installer.forge.run_subprocess_streaming", fake_run)
    monkeypatch.setattr("backend.server.installer.forge.is_windows", lambda: True)

    result = inst.install("1.20.1")
    assert result.success is True
    assert result.launch.args_file == (
        "libraries/net/minecraftforge/forge/1.20.1-47.4.10/win_args.txt"
    )


def test_install_falls_back_to_latest_when_no_recommended(
    tmp_path, monkeypatch
):
    """1.18.1 has only -latest — install should pick that build."""
    import subprocess
    from backend.server.installer.forge import ForgeInstaller
    inst = ForgeInstaller(tmp_path)
    _patch_session_with_install(inst, promotions={
        "promos": {"1.18.1-latest": "39.1.2"},
    })

    captured = {}
    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        # 1.18.1 is modern era (≥1.17).
        target = (tmp_path / "libraries" / "net" / "minecraftforge"
                  / "forge" / "1.18.1-39.1.2")
        target.mkdir(parents=True, exist_ok=True)
        (target / "unix_args.txt").write_text("# args\n")
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")
    monkeypatch.setattr("backend.server.installer.forge.run_subprocess_streaming", fake_run)
    monkeypatch.setattr("backend.server.installer.forge.is_windows", lambda: False)

    result = inst.install("1.18.1")
    assert result.success is True
    # Build URL should embed 39.1.2 (the latest pointer).
    jar_arg = captured["cmd"][captured["cmd"].index("-jar") + 1]
    assert "1.18.1-39.1.2" in jar_arg


def test_install_sha1_mismatch_aborts_before_subprocess(
    tmp_path, fake_promotions, monkeypatch
):
    """SHA1 mismatch unlinks the bad JAR and never invokes subprocess."""
    import subprocess
    from backend.server.installer.forge import ForgeInstaller
    inst = ForgeInstaller(tmp_path)

    bytes_payload = b"PKforgeINST"
    session = MagicMock()

    def get(url, **_):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.headers = {"Content-Length": str(len(bytes_payload))}
        if "promotions_slim.json" in url:
            resp.json.return_value = fake_promotions
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
    monkeypatch.setattr("backend.server.installer.forge.run_subprocess_streaming", fake_run)

    result = inst.install("1.20.1")
    assert result.success is False
    assert "sha1" in result.message.lower()
    assert subprocess_called["hit"] is False


# ---------- B10 Path-traversal mitigation (S1) ----------


def test_install_rejects_traversal_mc_version(tmp_path):
    """Sicherheit S1: ../-prefixed mc_version must be rejected at boundary."""
    from backend.server.installer.forge import ForgeInstaller
    inst = ForgeInstaller(tmp_path)

    result = inst.install("../../etc/passwd")
    assert result.success is False
    assert "mc_version" in result.message
    # No installer JAR should have been written anywhere under tmp_path.
    assert not list(tmp_path.glob("**/*.jar"))


def test_install_rejects_shell_metachar_mc_version(tmp_path):
    """A space + flag injected into mc_version must not reach the subprocess."""
    from backend.server.installer.forge import ForgeInstaller
    inst = ForgeInstaller(tmp_path)

    result = inst.install("1.20.1 --evil")
    assert result.success is False
    assert "mc_version" in result.message


def test_install_rejects_traversal_loader_version(tmp_path):
    """Caller-pinned loader_version is also whitelisted at the boundary."""
    from backend.server.installer.forge import ForgeInstaller
    inst = ForgeInstaller(tmp_path)

    result = inst.install("1.20.1", loader_version="../../bad")
    assert result.success is False
    assert "loader_version" in result.message


def test_install_rejects_poisoned_build_from_promotions(tmp_path):
    """Defence-in-depth: a third-party promotions JSON returning a poisoned
    ``build`` value (path-traversal in maven version) is rejected before
    the installer JAR download begins.
    """
    from backend.server.installer.forge import ForgeInstaller
    inst = ForgeInstaller(tmp_path)
    # Promotions returns a build that escapes the version-token allowlist.
    _patch_session_with_install(inst, promotions={
        "promos": {"1.20.1-recommended": "../../evil"},
    })

    result = inst.install("1.20.1")
    assert result.success is False
    assert "build" in result.message
    # Download path must NOT have materialised a jar outside install_path.
    assert not list(tmp_path.glob("**/forge-*.jar"))
