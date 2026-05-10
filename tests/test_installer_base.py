"""LaunchSpec dataclass + InstallResult serialization."""
from __future__ import annotations

import re
from unittest.mock import MagicMock

import pytest

from backend.server.installer.base import (
    InstallerBase,
    InstallResult,
    InstallStatus,
    LaunchSpec,
    _validate_version_token,
)


def test_launch_spec_to_dict_jar_type():
    spec = LaunchSpec(
        type="jar",
        jar="server.jar",
        jvm_args=[],
        program_args=["nogui"],
    )
    assert spec.to_dict() == {
        "type": "jar",
        "jar": "server.jar",
        "jvm_args": [],
        "program_args": ["nogui"],
        "args_file": None,
    }


def test_launch_spec_to_dict_copies_lists():
    """to_dict must not return references to the dataclass's internal lists."""
    jvm = ["-Dfoo=bar"]
    spec = LaunchSpec(type="jar", jar="server.jar", jvm_args=jvm, program_args=[])
    out = spec.to_dict()
    out["jvm_args"].append("MUTATED")
    assert spec.jvm_args == ["-Dfoo=bar"]


def test_install_result_to_dict_includes_launch():
    spec = LaunchSpec(
        type="jar",
        jar="server.jar",
        jvm_args=[],
        program_args=["nogui"],
    )
    result = InstallResult(
        success=True,
        status=InstallStatus.COMPLETED,
        message="ok",
        launch=spec,
    )
    payload = result.to_dict()
    assert payload["launch"] == {
        "type": "jar",
        "jar": "server.jar",
        "jvm_args": [],
        "program_args": ["nogui"],
        "args_file": None,
    }


def test_install_result_to_dict_launch_none_when_missing():
    result = InstallResult(
        success=False,
        status=InstallStatus.FAILED,
        message="boom",
    )
    assert result.to_dict()["launch"] is None


def test_fabric_installer_returns_launch_spec(tmp_path, monkeypatch):
    """Successful Fabric install returns a jar-type LaunchSpec."""
    from backend.server.installer.fabric import FabricInstaller

    inst = FabricInstaller(tmp_path)

    monkeypatch.setattr(inst, "_get_latest_loader_version", lambda mc: "0.16.0")
    monkeypatch.setattr(inst, "_get_latest_installer_version", lambda: "1.0.0")
    fake_jar = tmp_path / "server.jar"
    fake_jar.write_bytes(b"PK\x03\x04")
    monkeypatch.setattr(
        inst, "_download_server_jar", lambda mc, lv, iv, **kw: fake_jar
    )

    result = inst.install("1.21.4")

    assert result.success is True
    assert result.launch is not None
    assert result.launch.type == "jar"
    assert result.launch.jar == "server.jar"
    assert result.launch.program_args == ["nogui"]
    assert result.launch.jvm_args == []


def test_launch_spec_to_dict_args_file_type():
    spec = LaunchSpec(
        type="args_file",
        args_file="libraries/net/neoforged/neoforge/21.1.228/unix_args.txt",
        jvm_args=[],
        program_args=["nogui"],
    )
    assert spec.to_dict() == {
        "type": "args_file",
        "jar": None,
        "jvm_args": [],
        "program_args": ["nogui"],
        "args_file": "libraries/net/neoforged/neoforge/21.1.228/unix_args.txt",
    }


def test_launch_spec_to_dict_jar_type_includes_null_args_file():
    """Existing jar-type specs must include args_file=None in their dict form."""
    spec = LaunchSpec(
        type="jar",
        jar="server.jar",
        jvm_args=[],
        program_args=["nogui"],
    )
    assert spec.to_dict()["args_file"] is None


def test_installer_base_requires_java_for_install_default_false(tmp_path):
    from backend.server.installer.fabric import FabricInstaller
    assert FabricInstaller(tmp_path).requires_java_for_install is False


def test_vanilla_installer_requires_java_for_install_default_false(tmp_path):
    from backend.server.installer.vanilla import VanillaInstaller
    assert VanillaInstaller(tmp_path).requires_java_for_install is False


def test_installer_base_java_exec_default_none(tmp_path):
    from backend.server.installer.fabric import FabricInstaller
    inst = FabricInstaller(tmp_path)
    assert inst.java_exec is None


def test_installer_base_set_java_exec_records_path(tmp_path):
    from backend.server.installer.fabric import FabricInstaller
    inst = FabricInstaller(tmp_path)
    inst.set_java_exec("/var/lib/fabricator/java/jdk-21/bin/java")
    assert inst.java_exec == "/var/lib/fabricator/java/jdk-21/bin/java"


def test_installer_base_set_java_exec_accepts_none(tmp_path):
    """Clearing the Java path is supported — unsets any prior value."""
    from backend.server.installer.fabric import FabricInstaller
    inst = FabricInstaller(tmp_path)
    inst.set_java_exec("/path/to/java")
    inst.set_java_exec(None)
    assert inst.java_exec is None


# ---------- Canonical MC version form ----------
#
# Modrinth and other downstream consumers tag x.y.0 MC releases with the
# bare "x.y" form. Loaders whose own APIs return the explicit "x.y.0"
# form (notably NeoForge) must canonicalize before returning so all
# loaders surface the same form. These tests pin that invariant.


_X_Y_ZERO_RE = re.compile(r"^[a-z]?\d+\.\d+\.0$")


@pytest.mark.parametrize("raw,expected", [
    ("1.21.0", "1.21"),
    ("1.20.1", "1.20.1"),
    ("1.21", "1.21"),
    ("a1.2.0", "a1.2"),
    ("26.2-snapshot-6", "26.2-snapshot-6"),
])
def test_canonicalize_mc_version(raw, expected):
    assert InstallerBase._canonicalize_mc_version(raw) == expected


def _assert_no_zero_patch(versions):
    offenders = [v["version"] for v in versions if _X_Y_ZERO_RE.match(v.get("version", ""))]
    assert offenders == [], f"x.y.0 entries leaked from get_minecraft_versions: {offenders}"


def test_vanilla_get_minecraft_versions_no_zero_patch(tmp_path):
    """Vanilla legacy entries like 'a1.2.0' must canonicalize before surfacing."""
    from backend.server.installer.vanilla import VanillaInstaller
    inst = VanillaInstaller(tmp_path)

    session = MagicMock()
    manifest = {
        "latest": {"release": "1.21.4", "snapshot": "24w45a"},
        "versions": [
            {"id": "1.21.4", "type": "release", "url": "x"},
            {"id": "1.21.0", "type": "release", "url": "x"},
            {"id": "a1.2.0", "type": "old_alpha", "url": "x"},
        ],
    }

    def get(url, **_):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = manifest
        return resp

    session.get.side_effect = get
    inst.session = session

    _assert_no_zero_patch(inst.get_minecraft_versions())


def test_fabric_get_minecraft_versions_no_zero_patch(tmp_path):
    from backend.server.installer.fabric import FabricInstaller
    inst = FabricInstaller(tmp_path)

    session = MagicMock()
    payload = [
        {"version": "1.21.4", "stable": True},
        {"version": "1.21.0", "stable": True},
        {"version": "1.21", "stable": True},
    ]

    def get(url, **_):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = payload
        return resp

    session.get.side_effect = get
    inst.session = session

    _assert_no_zero_patch(inst.get_minecraft_versions())


def test_quilt_get_minecraft_versions_no_zero_patch(tmp_path):
    from backend.server.installer.quilt import QuiltInstaller
    inst = QuiltInstaller(tmp_path)

    session = MagicMock()
    payload = [
        {"version": "1.21.4", "stable": True},
        {"version": "1.21.0", "stable": True},
    ]

    def get(url, **_):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = payload
        return resp

    session.get.side_effect = get
    inst.session = session

    _assert_no_zero_patch(inst.get_minecraft_versions())


def test_forge_get_minecraft_versions_no_zero_patch(tmp_path):
    """Forge promotions has a few legacy x.y.0 entries (e.g. 1.4.0)."""
    from backend.server.installer.forge import ForgeInstaller
    inst = ForgeInstaller(tmp_path)

    session = MagicMock()
    promotions = {
        "promos": {
            "1.21.4-latest": "54.1.16",
            "1.4.0-latest": "6.0.0.0",
            "1.20.1-recommended": "47.4.10",
        },
    }

    def get(url, **_):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = promotions
        return resp

    session.get.side_effect = get
    inst.session = session

    _assert_no_zero_patch(inst.get_minecraft_versions())


def test_neoforge_get_minecraft_versions_no_zero_patch(tmp_path):
    """The bug fix: NeoForge's 21.0.x → MC 1.21.0 must canonicalize to '1.21'."""
    from backend.server.installer.neoforge import NeoForgeInstaller
    inst = NeoForgeInstaller(tmp_path)

    session = MagicMock()
    payload = {
        "isSnapshot": False,
        "versions": ["21.0.143", "21.1.228", "26.1.2.43-beta"],
    }

    def get(url, **_):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = payload
        return resp

    session.get.side_effect = get
    inst.session = session

    _assert_no_zero_patch(inst.get_minecraft_versions())


# ---------- B10 Path-traversal mitigation (S1 + S5) ----------
#
# These tests pin the trust-boundary contract that closes Sicherheits-Block
# S1 (Forge mc_version/build) and S5 (NeoForge / Quilt loader_version /
# install-dir): every externally-controlled version token is whitelisted by
# ``_validate_version_token`` before it lands in a filename or subprocess
# arg, and every path constructed from those tokens is re-checked under
# ``install_path`` by ``_resolve_within_install_path``.


@pytest.mark.parametrize("good", [
    "1.20.1",
    "1.21",
    "b1.7.3",
    "21.1.228",
    "54.1.16",
    "1.21.4-rc1",
    "0.27.0",
    "26.1.2.43-beta",
    "10.13.4.1614",
])
def test_validate_version_token_accepts_real_version_shapes(good):
    assert _validate_version_token(good, field_name="mc_version") == good


@pytest.mark.parametrize("bad", [
    "../../etc/passwd",
    "..",
    "../1.20.1",
    "1.20.1/..",
    "1.20.1 --evil",
    "1.20.1\nrm -rf /",
    "1.20.1; rm -rf /",
    "1.20.1\\..",
    "",
    "1.20.1\x00",
    "1.20.1/extra",
])
def test_validate_version_token_rejects_path_and_shell_metachars(bad):
    with pytest.raises(ValueError, match="Invalid mc_version"):
        _validate_version_token(bad, field_name="mc_version")


def test_validate_version_token_rejects_non_string():
    with pytest.raises(ValueError, match="Invalid build"):
        _validate_version_token(None, field_name="build")  # type: ignore[arg-type]


def test_validate_version_token_field_name_in_error_message():
    """Error must name the field so install routes can log a clear failure."""
    with pytest.raises(ValueError, match="loader_version"):
        _validate_version_token("..", field_name="loader_version")


def test_resolve_within_install_path_returns_resolved_descendant(tmp_path):
    from backend.server.installer.fabric import FabricInstaller
    inst = FabricInstaller(tmp_path)

    out = inst._resolve_within_install_path("forge-1.20.1-47.4.10-installer.jar")
    assert out == (tmp_path / "forge-1.20.1-47.4.10-installer.jar").resolve()
    # Result is always under the install path.
    assert out.is_relative_to(tmp_path.resolve())


def test_resolve_within_install_path_accepts_nested_segments(tmp_path):
    from backend.server.installer.fabric import FabricInstaller
    inst = FabricInstaller(tmp_path)

    out = inst._resolve_within_install_path(
        "libraries", "net", "neoforged", "neoforge", "21.1.228", "unix_args.txt"
    )
    expected = (
        tmp_path / "libraries" / "net" / "neoforged" / "neoforge"
        / "21.1.228" / "unix_args.txt"
    ).resolve()
    assert out == expected


def test_resolve_within_install_path_rejects_parent_traversal(tmp_path):
    from backend.server.installer.fabric import FabricInstaller
    inst = FabricInstaller(tmp_path)

    with pytest.raises(ValueError, match="escapes install_path"):
        inst._resolve_within_install_path("..", "etc", "passwd")


def test_resolve_within_install_path_rejects_absolute_segment(tmp_path):
    """An absolute path part replaces the prior parts under pathlib semantics."""
    from backend.server.installer.fabric import FabricInstaller
    inst = FabricInstaller(tmp_path)

    with pytest.raises(ValueError, match="escapes install_path"):
        inst._resolve_within_install_path("/etc/passwd")


def test_resolve_within_install_path_rejects_sibling_prefix(tmp_path):
    """A sibling dir whose name is a prefix of install_path must not pass."""
    from backend.server.installer.fabric import FabricInstaller
    sibling = tmp_path / "sibling"
    sibling.mkdir()
    inst = FabricInstaller(sibling)

    with pytest.raises(ValueError, match="escapes install_path"):
        # ../sibling-evil-suffix would resolve to a path that *starts* with
        # str(sibling) but isn't under it. relative_to() catches this.
        inst._resolve_within_install_path("..", "sibling-evil-suffix")


def test_resolve_within_install_path_zero_parts_returns_install_root(tmp_path):
    """Calling with no parts returns the resolved install_path itself."""
    from backend.server.installer.fabric import FabricInstaller
    inst = FabricInstaller(tmp_path)

    out = inst._resolve_within_install_path()
    assert out == tmp_path.resolve()
