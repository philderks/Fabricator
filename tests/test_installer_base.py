"""LaunchSpec dataclass + InstallResult serialization."""
from __future__ import annotations

from backend.server.installer.base import (
    InstallResult,
    InstallStatus,
    LaunchSpec,
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
        inst, "_download_server_jar", lambda mc, lv, iv: fake_jar
    )

    result = inst.install("1.21.4")

    assert result.success is True
    assert result.launch is not None
    assert result.launch.type == "jar"
    assert result.launch.jar == "server.jar"
    assert result.launch.program_args == ["nogui"]
    assert result.launch.jvm_args == []
