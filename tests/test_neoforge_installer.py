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
    # 21.0.143 stable + 21.0.142-beta → 1.21 (canonical bare form;
    # stable=True since at least one stable release exists)
    assert "1.21" in mc_strings
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


def test_install_picks_latest_stable_when_unspecified(tmp_path, fake_maven_versions, monkeypatch):
    """install(mc_version) without loader_version selects latest stable for that MC."""
    import subprocess
    from backend.server.installer.neoforge import NeoForgeInstaller
    inst = NeoForgeInstaller(tmp_path)
    _patch_session(inst, maven_response=fake_maven_versions)

    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["cwd"] = kwargs.get("cwd")
        chosen_version = "21.1.228"  # latest stable for 1.21.1 in the fixture
        target_dir = tmp_path / "libraries" / "net" / "neoforged" / "neoforge" / chosen_version
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / "unix_args.txt").write_text("# args\n")
        (target_dir / "win_args.txt").write_text("@@ args\n")
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr("backend.server.installer.neoforge.run_subprocess_streaming", fake_run)
    monkeypatch.setattr("backend.server.installer.neoforge.is_windows", lambda: False)

    result = inst.install("1.21.1")

    assert result.success is True
    assert result.launch is not None
    assert result.launch.type == "args_file"
    expected = "libraries/net/neoforged/neoforge/21.1.228/unix_args.txt"
    assert result.launch.args_file == expected
    assert result.launch.program_args == ["nogui"]
    assert (tmp_path / "eula.txt").read_text().strip() == "eula=true"
    assert captured["cmd"][0] == "java"
    assert "--installServer" in captured["cmd"]
    assert str(captured["cwd"]) == str(tmp_path)


def test_install_uses_set_java_exec_path_for_subprocess(tmp_path, fake_maven_versions, monkeypatch):
    """When set_java_exec was called, the subprocess invokes that exact path."""
    import subprocess
    from backend.server.installer.neoforge import NeoForgeInstaller
    inst = NeoForgeInstaller(tmp_path)
    _patch_session(inst, maven_response=fake_maven_versions)
    inst.set_java_exec("/var/lib/fabricator/java/jdk-21/bin/java")

    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        chosen_version = "21.1.228"
        target_dir = tmp_path / "libraries" / "net" / "neoforged" / "neoforge" / chosen_version
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / "unix_args.txt").write_text("# args\n")
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    monkeypatch.setattr("backend.server.installer.neoforge.run_subprocess_streaming", fake_run)
    monkeypatch.setattr("backend.server.installer.neoforge.is_windows", lambda: False)

    result = inst.install("1.21.1")
    assert result.success is True
    assert captured["cmd"][0] == "/var/lib/fabricator/java/jdk-21/bin/java"


def test_install_uses_windows_args_file_on_windows(tmp_path, fake_maven_versions, monkeypatch):
    import subprocess
    from backend.server.installer.neoforge import NeoForgeInstaller
    inst = NeoForgeInstaller(tmp_path)
    _patch_session(inst, maven_response=fake_maven_versions)

    def fake_run(cmd, **kwargs):
        chosen_version = "21.1.228"
        target_dir = tmp_path / "libraries" / "net" / "neoforged" / "neoforge" / chosen_version
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / "win_args.txt").write_text("@@ win args\n")
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    monkeypatch.setattr("backend.server.installer.neoforge.run_subprocess_streaming", fake_run)
    monkeypatch.setattr("backend.server.installer.neoforge.is_windows", lambda: True)

    result = inst.install("1.21.1")
    assert result.success is True
    assert result.launch.args_file == (
        "libraries/net/neoforged/neoforge/21.1.228/win_args.txt"
    )


def test_install_subprocess_failure_returns_failure(tmp_path, fake_maven_versions, monkeypatch):
    import subprocess
    from backend.server.installer.neoforge import NeoForgeInstaller
    inst = NeoForgeInstaller(tmp_path)
    _patch_session(inst, maven_response=fake_maven_versions)

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(args=cmd, returncode=2, stdout="", stderr="installer exploded")

    monkeypatch.setattr("backend.server.installer.neoforge.run_subprocess_streaming", fake_run)
    monkeypatch.setattr("backend.server.installer.neoforge.is_windows", lambda: False)

    result = inst.install("1.21.1")
    assert result.success is False
    assert "installer exploded" in result.message or "returncode 2" in result.message


def test_install_args_file_missing_after_install_returns_failure(tmp_path, fake_maven_versions, monkeypatch):
    """If the installer succeeds but the args file is absent, fail loudly."""
    import subprocess
    from backend.server.installer.neoforge import NeoForgeInstaller
    inst = NeoForgeInstaller(tmp_path)
    _patch_session(inst, maven_response=fake_maven_versions)

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    monkeypatch.setattr("backend.server.installer.neoforge.run_subprocess_streaming", fake_run)
    monkeypatch.setattr("backend.server.installer.neoforge.is_windows", lambda: False)

    result = inst.install("1.21.1")
    assert result.success is False
    assert "args_file" in result.message.lower() or "args file" in result.message.lower()


def test_install_unknown_mc_version_fails(tmp_path, fake_maven_versions):
    from backend.server.installer.neoforge import NeoForgeInstaller
    inst = NeoForgeInstaller(tmp_path)
    _patch_session(inst, maven_response=fake_maven_versions)

    result = inst.install("1.19.4")
    assert result.success is False
    assert "1.19.4" in result.message


def test_install_sha1_mismatch_fails(tmp_path, fake_maven_versions, monkeypatch):
    import subprocess
    from backend.server.installer.neoforge import NeoForgeInstaller
    inst = NeoForgeInstaller(tmp_path)

    session = MagicMock()
    bytes_payload = b"PKneoforgeINST"

    def get(url, **_):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.headers = {"Content-Length": str(len(bytes_payload))}
        if "api/maven/versions/releases" in url:
            resp.json.return_value = fake_maven_versions
        elif url.endswith(".jar"):
            resp.iter_content = lambda chunk_size=8192: iter([bytes_payload])
            resp.__enter__ = lambda s: s
            resp.__exit__ = lambda *a: False
        elif url.endswith(".sha1"):
            resp.text = "deadbeef" * 5  # 40 chars, intentionally wrong
        return resp

    session.get.side_effect = get
    inst.session = session

    monkeypatch.setattr("backend.server.installer.neoforge.run_subprocess_streaming",
                        lambda *a, **k: subprocess.CompletedProcess(args=[], returncode=0))

    result = inst.install("1.21.1")
    assert result.success is False
    assert "sha1" in result.message.lower()


def test_install_with_config_writes_server_properties_and_returns_launch(
    tmp_path, fake_maven_versions, monkeypatch
):
    """install_with_config delegates to install() and then writes server.properties.

    Composition contract: success path returns the same launch spec as
    install(), populates details["server_properties"], and writes the
    properties file with values derived from server_config.
    """
    import subprocess
    from backend.server.installer.neoforge import NeoForgeInstaller
    inst = NeoForgeInstaller(tmp_path)
    _patch_session(inst, maven_response=fake_maven_versions)

    def fake_run(cmd, **kwargs):
        chosen_version = "21.1.228"
        target_dir = tmp_path / "libraries" / "net" / "neoforged" / "neoforge" / chosen_version
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / "unix_args.txt").write_text("# args\n")
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    monkeypatch.setattr("backend.server.installer.neoforge.run_subprocess_streaming", fake_run)
    monkeypatch.setattr("backend.server.installer.neoforge.is_windows", lambda: False)

    server_config = {
        "port": 25570,
        "motd": "Fabricator NeoForge Test",
        "maxPlayers": 12,
        "difficulty": "hard",
    }

    result = inst.install_with_config("1.21.1", server_config)

    assert result.success is True
    assert result.launch is not None
    assert result.launch.type == "args_file"
    assert result.launch.args_file == (
        "libraries/net/neoforged/neoforge/21.1.228/unix_args.txt"
    )

    props_path = tmp_path / "server.properties"
    assert props_path.exists()
    props_text = props_path.read_text()
    assert "server-port=25570" in props_text
    assert "motd=Fabricator NeoForge Test" in props_text
    assert "max-players=12" in props_text
    assert "difficulty=hard" in props_text

    assert result.details is not None
    assert result.details["server_properties"] == str(props_path)


def test_install_with_config_failure_does_not_write_server_properties(
    tmp_path, fake_maven_versions, monkeypatch
):
    """When install() fails, install_with_config short-circuits and writes no properties."""
    import subprocess
    from backend.server.installer.neoforge import NeoForgeInstaller
    inst = NeoForgeInstaller(tmp_path)
    _patch_session(inst, maven_response=fake_maven_versions)

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(
            args=cmd, returncode=2, stdout="", stderr="installer crashed"
        )

    monkeypatch.setattr("backend.server.installer.neoforge.run_subprocess_streaming", fake_run)
    monkeypatch.setattr("backend.server.installer.neoforge.is_windows", lambda: False)

    result = inst.install_with_config("1.21.1", {"port": 25570})

    assert result.success is False
    # No server.properties side-effect on the failure path.
    assert not (tmp_path / "server.properties").exists()


def test_install_with_config_emits_progress_phases(
    tmp_path, fake_maven_versions, monkeypatch
):
    """Progress callback receives the documented phase sequence in monotonic order.

    Pins both membership AND ordering — a regression that emits e.g.
    ``writing_eula`` before ``running_installer`` would silently break the
    UI's progress bar. ``phases.index(...)`` is used so a duplicate emission
    of the same phase still pins the FIRST occurrence's relative position.
    """
    import subprocess
    from backend.server.installer.neoforge import NeoForgeInstaller
    inst = NeoForgeInstaller(tmp_path)
    _patch_session(inst, maven_response=fake_maven_versions)

    def fake_run(cmd, **kwargs):
        chosen_version = "21.1.228"
        target_dir = tmp_path / "libraries" / "net" / "neoforged" / "neoforge" / chosen_version
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / "unix_args.txt").write_text("# args\n")
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    monkeypatch.setattr("backend.server.installer.neoforge.run_subprocess_streaming", fake_run)
    monkeypatch.setattr("backend.server.installer.neoforge.is_windows", lambda: False)

    events: list[tuple[str, dict]] = []

    def cb(phase, detail):
        events.append((phase, dict(detail)))

    result = inst.install_with_config("1.21.1", {"port": 25565}, progress_callback=cb)
    assert result.success is True

    phases = [phase for phase, _ in events]
    assert phases[0] == "starting"
    assert phases[-1] == "done"
    assert "failed" not in phases

    # Monotonic ordering of all 5 install() phases plus install_with_config's
    # writing_eula. Each phase must appear and earlier ones must precede later.
    expected_sequence = [
        "starting",
        "resolving_versions",
        "running_installer",
        "detecting_artifacts",
        "writing_eula",
    ]
    indices = [phases.index(p) for p in expected_sequence]
    assert indices == sorted(indices), (
        f"phase sequence not monotonic: {list(zip(expected_sequence, indices))}\n"
        f"all phases: {phases}"
    )


# ---------- B15.5a: parametrized failure-mode property ----------


def _setup_subprocess_timeout(inst, monkeypatch):
    """The subprocess invocation raises SubprocessTimeout."""
    from backend.server.installer.base import SubprocessTimeout

    def boom(*args, **kwargs):
        raise SubprocessTimeout("installer wedged at 1800s")

    monkeypatch.setattr("backend.server.installer.neoforge.run_subprocess_streaming", boom)
    monkeypatch.setattr("backend.server.installer.neoforge.is_windows", lambda: False)


def _setup_subprocess_oserror(inst, monkeypatch):
    """The subprocess can't be invoked (e.g. java binary missing)."""
    def boom(*args, **kwargs):
        raise OSError("[Errno 2] No such file or directory: 'java'")

    monkeypatch.setattr("backend.server.installer.neoforge.run_subprocess_streaming", boom)
    monkeypatch.setattr("backend.server.installer.neoforge.is_windows", lambda: False)


def _setup_empty_maven(inst, monkeypatch):
    """Maven returns an empty version list — no loader_version resolvable."""
    monkeypatch.setattr(inst, "_fetch_maven_versions", lambda: [])


def _setup_unknown_mc_version(inst, monkeypatch):
    """The requested mc_version has no NeoForge release."""
    # Default fixture has no 1.19.4-era releases (all are 20.x+/21.x+/26.x).
    # The install() call uses mc_version="1.19.4" so loader_version resolution fails.
    pass


def _setup_missing_args_file(inst, monkeypatch):
    """Subprocess returns 0 but does not create the args_file artefact."""
    import subprocess

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    monkeypatch.setattr("backend.server.installer.neoforge.run_subprocess_streaming", fake_run)
    monkeypatch.setattr("backend.server.installer.neoforge.is_windows", lambda: False)


@pytest.mark.parametrize(
    ("scenario", "setup", "mc_version", "expected_substring"),
    [
        ("subprocess_timeout",   _setup_subprocess_timeout,   "1.21.1", "timed out"),
        ("subprocess_oserror",   _setup_subprocess_oserror,   "1.21.1", "invoke"),
        ("empty_maven",          _setup_empty_maven,          "1.21.1", "could not fetch"),
        ("unknown_mc_version",   _setup_unknown_mc_version,   "1.19.4", "1.19.4"),
        ("missing_args_file",    _setup_missing_args_file,    "1.21.1", "args_file"),
    ],
)
def test_install_with_config_failure_modes_dont_write_server_properties(
    tmp_path, fake_maven_versions, monkeypatch, scenario, setup, mc_version, expected_substring
):
    """Failure-mode property: on ANY failure path, server.properties stays absent.

    Pins the no-side-effect contract: a failed install_with_config must not
    write a partial properties file that a subsequent start would pick up.
    """
    from backend.server.installer.neoforge import NeoForgeInstaller
    inst = NeoForgeInstaller(tmp_path)
    _patch_session(inst, maven_response=fake_maven_versions)

    setup(inst, monkeypatch)

    result = inst.install_with_config(mc_version, {"port": 25570})

    assert result.success is False, f"{scenario}: install_with_config should have failed"
    assert expected_substring.lower() in result.message.lower(), (
        f"{scenario}: expected {expected_substring!r} in message, got {result.message!r}"
    )
    # Property assertion: no server.properties leak on the failure path.
    assert not (tmp_path / "server.properties").exists(), (
        f"{scenario}: server.properties was written on a failure path"
    )


def test_install_subprocess_uses_no_window_kwargs(tmp_path, fake_maven_versions, monkeypatch):
    """The installer subprocess must opt into platform_utils.subprocess_no_window_kwargs.

    Without this the NeoForge installer flashes a console window on Windows,
    breaking the convention every other subprocess in the codebase follows.
    """
    import subprocess
    from backend.server.installer.neoforge import NeoForgeInstaller
    inst = NeoForgeInstaller(tmp_path)
    _patch_session(inst, maven_response=fake_maven_versions)

    captured_kwargs = {}

    def fake_run(cmd, **kwargs):
        captured_kwargs.update(kwargs)
        chosen_version = "21.1.228"
        target_dir = tmp_path / "libraries" / "net" / "neoforged" / "neoforge" / chosen_version
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / "unix_args.txt").write_text("# args\n")
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    # Sentinel kwargs returned by subprocess_no_window_kwargs — verifies the
    # NeoForgeInstaller called the helper and merged the result.
    SENTINEL_KW = {"creationflags": 0x08000000}
    monkeypatch.setattr(
        "backend.server.installer.neoforge.platform_utils.subprocess_no_window_kwargs",
        lambda: SENTINEL_KW,
    )
    monkeypatch.setattr("backend.server.installer.neoforge.run_subprocess_streaming", fake_run)
    monkeypatch.setattr("backend.server.installer.neoforge.is_windows", lambda: False)

    result = inst.install("1.21.1")
    assert result.success is True
    # The sentinel kwarg must have made it through.
    assert captured_kwargs.get("creationflags") == 0x08000000


# ---------- B10 Path-traversal mitigation (S5) ----------


def test_install_rejects_traversal_mc_version(tmp_path):
    """Sicherheit S5: ../-prefixed mc_version must be rejected at boundary."""
    from backend.server.installer.neoforge import NeoForgeInstaller
    inst = NeoForgeInstaller(tmp_path)

    result = inst.install("../../etc/passwd")
    assert result.success is False
    assert "mc_version" in result.message
    assert not list(tmp_path.glob("**/*.jar"))


def test_install_rejects_shell_metachar_loader_version(tmp_path):
    """A caller-pinned loader_version with shell metachars must not pass."""
    from backend.server.installer.neoforge import NeoForgeInstaller
    inst = NeoForgeInstaller(tmp_path)

    result = inst.install("1.21.1", loader_version="21.1.228 --evil")
    assert result.success is False
    assert "loader_version" in result.message


def test_install_rejects_traversal_loader_version(tmp_path):
    from backend.server.installer.neoforge import NeoForgeInstaller
    inst = NeoForgeInstaller(tmp_path)

    result = inst.install("1.21.1", loader_version="../../bad")
    assert result.success is False
    assert "loader_version" in result.message
