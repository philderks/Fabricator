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
