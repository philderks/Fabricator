"""ServerProcessRegistry._build_command honours persisted launch."""
from __future__ import annotations


def _make_registry(tmp_path):
    from backend.server.registry import ServerProcessRegistry
    return ServerProcessRegistry(tmp_path)


def test_build_command_uses_persisted_jar_launch(tmp_path, monkeypatch):
    reg = _make_registry(tmp_path)
    monkeypatch.setattr(reg, "_resolve_java_exec", lambda s: "/opt/java/bin/java")

    server = {
        "id": "srv_x",
        "memory": 3,
        "launch": {
            "type": "jar",
            "jar": "server.jar",
            "jvm_args": [],
            "program_args": ["nogui"],
        },
    }
    cmd = reg._build_command(server)
    assert cmd == [
        "/opt/java/bin/java",
        "-Xms3G",
        "-Xmx3G",
        "-jar",
        "server.jar",
        "nogui",
    ]


def test_build_command_jar_launch_with_extra_jvm_args(tmp_path, monkeypatch):
    reg = _make_registry(tmp_path)
    monkeypatch.setattr(reg, "_resolve_java_exec", lambda s: "java")

    server = {
        "id": "srv_x",
        "memory": 4,
        "launch": {
            "type": "jar",
            "jar": "server.jar",
            "jvm_args": ["-Dlog4j2.formatMsgNoLookups=true"],
            "program_args": ["nogui"],
        },
    }
    cmd = reg._build_command(server)
    assert cmd == [
        "java",
        "-Xms4G",
        "-Xmx4G",
        "-Dlog4j2.formatMsgNoLookups=true",
        "-jar",
        "server.jar",
        "nogui",
    ]


def test_build_command_legacy_fallback_when_launch_missing(tmp_path, monkeypatch):
    """A server record without a 'launch' key uses the legacy default."""
    reg = _make_registry(tmp_path)
    monkeypatch.setattr(reg, "_resolve_java_exec", lambda s: "java")

    server = {"id": "srv_x", "memory": 4}
    cmd = reg._build_command(server)
    assert cmd == ["java", "-Xms4G", "-Xmx4G", "-jar", "server.jar", "nogui"]


def test_build_command_explicit_command_override_wins(tmp_path):
    reg = _make_registry(tmp_path)
    server = {
        "id": "srv_x",
        "command": ["bash", "run.sh"],
        "launch": {
            "type": "jar",
            "jar": "server.jar",
            "jvm_args": [],
            "program_args": ["nogui"],
        },
    }
    assert reg._build_command(server) == ["bash", "run.sh"]


def test_build_command_unknown_launch_type_raises(tmp_path, monkeypatch):
    """Unknown launch.type must raise — silent legacy-fallback hides bugs."""
    import pytest
    reg = _make_registry(tmp_path)
    monkeypatch.setattr(reg, "_resolve_java_exec", lambda s: "java")

    server = {
        "id": "srv_future",
        "memory": 4,
        "launch": {"type": "args_files", "jar": None},
    }
    with pytest.raises(ValueError, match="Unknown launch.type"):
        reg._build_command(server)


def test_build_command_explicit_empty_program_args_is_respected(tmp_path, monkeypatch):
    """program_args=[] means 'no program args' — must not be replaced with ['nogui']."""
    reg = _make_registry(tmp_path)
    monkeypatch.setattr(reg, "_resolve_java_exec", lambda s: "java")

    server = {
        "id": "srv_x",
        "memory": 2,
        "launch": {
            "type": "jar",
            "jar": "server.jar",
            "jvm_args": [],
            "program_args": [],
        },
    }
    cmd = reg._build_command(server)
    assert cmd == ["java", "-Xms2G", "-Xmx2G", "-jar", "server.jar"]


def test_build_command_args_file_launch(tmp_path, monkeypatch):
    reg = _make_registry(tmp_path)
    monkeypatch.setattr(reg, "_resolve_java_exec", lambda s: "/opt/java/bin/java")

    server = {
        "id": "srv_n",
        "memory": 6,
        "launch": {
            "type": "args_file",
            "args_file": "libraries/net/neoforged/neoforge/21.1.228/unix_args.txt",
            "jvm_args": [],
            "program_args": ["nogui"],
        },
    }
    cmd = reg._build_command(server)
    assert cmd == [
        "/opt/java/bin/java",
        "-Xms6G",
        "-Xmx6G",
        "@libraries/net/neoforged/neoforge/21.1.228/unix_args.txt",
        "nogui",
    ]


def test_build_command_args_file_jvm_args_includes_extra_jvm_flags(tmp_path, monkeypatch):
    """Extra jvm_args persisted on the launch must end up before the @args_file token."""
    reg = _make_registry(tmp_path)
    monkeypatch.setattr(reg, "_resolve_java_exec", lambda s: "java")

    server = {
        "id": "srv_n",
        "memory": 4,
        "launch": {
            "type": "args_file",
            "args_file": "libraries/net/neoforged/neoforge/21.1.228/win_args.txt",
            "jvm_args": ["-Dlog4j2.formatMsgNoLookups=true"],
            "program_args": ["nogui"],
        },
    }
    cmd = reg._build_command(server)
    # The args file produced by the NeoForge installer (unix_args.txt /
    # win_args.txt) only contains classpath + main-class — never -Xmx.
    # NeoForge's user_jvm_args.txt is intentionally NOT referenced (D1):
    # Fabricator owns memory directly via -Xms/-Xmx, and any GC tuning
    # someone wants belongs in the per-server `command` override field.
    # So there is no JVM flag conflict here — these tokens are simply the
    # only memory directives the JVM ever sees.
    assert cmd == [
        "java",
        "-Xms4G",
        "-Xmx4G",
        "-Dlog4j2.formatMsgNoLookups=true",
        "@libraries/net/neoforged/neoforge/21.1.228/win_args.txt",
        "nogui",
    ]


def test_build_command_args_file_missing_path_raises(tmp_path, monkeypatch):
    """A persisted args_file launch with no path is a corrupted record — fail loudly."""
    import pytest
    reg = _make_registry(tmp_path)
    monkeypatch.setattr(reg, "_resolve_java_exec", lambda s: "java")

    server = {
        "id": "srv_n",
        "memory": 4,
        "launch": {"type": "args_file", "args_file": None, "jvm_args": [], "program_args": ["nogui"]},
    }
    with pytest.raises(ValueError, match="args_file"):
        reg._build_command(server)
