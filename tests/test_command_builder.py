"""ServerProcessRegistry._build_command honours persisted launch.

C3 (managed mode) accepted residual: when FABRICATOR_MANAGED is on, the pinned
-Xms/-Xmx land in their normal slot BEFORE any @args_file and any record-supplied
command / javaPath / launch.jvm_args are dropped at the source. Fabricator never
parses or regenerates the args_file, so an -Xmx embedded INSIDE a Forge/NeoForge
args_file (writable via files/content, a modpack override, or a restore) still
wins in JVM argv order. This is accepted: the blast radius is the customer's own
single-tenant VM and the physical VM RAM is the real enforcement layer — the pin
is a belt, not the boundary. The managed args_file test below asserts the true
argv only, never an ordering the JVM does not honour.
"""
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


def test_build_command_memory_unit_mb_uses_m_suffix(tmp_path, monkeypatch):
    """memoryUnit='MB' emits -Xms/-Xmx with an M suffix and the raw value."""
    reg = _make_registry(tmp_path)
    monkeypatch.setattr(reg, "_resolve_java_exec", lambda s: "java")

    server = {
        "id": "srv_x",
        "memory": 1536,
        "memoryUnit": "MB",
        "launch": {
            "type": "jar",
            "jar": "server.jar",
            "jvm_args": [],
            "program_args": ["nogui"],
        },
    }
    cmd = reg._build_command(server)
    assert cmd == ["java", "-Xms1536M", "-Xmx1536M", "-jar", "server.jar", "nogui"]


def test_build_command_memory_unit_defaults_to_gb(tmp_path, monkeypatch):
    """A record with no memoryUnit (legacy) keeps the G suffix."""
    reg = _make_registry(tmp_path)
    monkeypatch.setattr(reg, "_resolve_java_exec", lambda s: "java")

    server = {"id": "srv_x", "memory": 4}
    cmd = reg._build_command(server)
    assert cmd == ["java", "-Xms4G", "-Xmx4G", "-jar", "server.jar", "nogui"]


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


# ── C3: managed memory pin + source-neutralization + fail-closed ──────────────

def test_managed_pins_heap_and_ignores_record_overrides(tmp_path, monkeypatch):
    """Managed jar launch: heap pinned to the env value; record memory,
    javaPath and launch.jvm_args are all dropped at the source."""
    monkeypatch.setenv("FABRICATOR_MANAGED", "1")
    monkeypatch.setenv("FABRICATOR_MANAGED_MEMORY_GB", "8")
    reg = _make_registry(tmp_path)
    # Mirror the real precedence so a surviving javaPath would show up as argv[0].
    monkeypatch.setattr(reg, "_resolve_java_exec", lambda s: s.get("javaPath") or "managed-java")

    server = {
        "id": "srv_x",
        "memory": 3,
        "memoryUnit": "MB",
        "javaPath": "/evil/java",
        "launch": {
            "type": "jar",
            "jar": "server.jar",
            "jvm_args": ["-Xmx99G"],
            "program_args": ["nogui"],
        },
    }
    cmd = reg._build_command(server)
    assert cmd == ["managed-java", "-Xms8G", "-Xmx8G", "-jar", "server.jar", "nogui"]


def test_managed_ignores_custom_command(tmp_path, monkeypatch):
    """A record `command` (full launch-line takeover, no -Xmx) is ignored."""
    monkeypatch.setenv("FABRICATOR_MANAGED", "1")
    monkeypatch.setenv("FABRICATOR_MANAGED_MEMORY_GB", "8")
    reg = _make_registry(tmp_path)
    monkeypatch.setattr(reg, "_resolve_java_exec", lambda s: "managed-java")

    server = {
        "id": "srv_x",
        "command": ["bash", "evil.sh"],
        "launch": {"type": "jar", "jar": "server.jar", "jvm_args": [], "program_args": ["nogui"]},
    }
    cmd = reg._build_command(server)
    assert cmd == ["managed-java", "-Xms8G", "-Xmx8G", "-jar", "server.jar", "nogui"]
    assert "bash" not in cmd


def test_managed_legacy_branch_pins_heap(tmp_path, monkeypatch):
    monkeypatch.setenv("FABRICATOR_MANAGED", "1")
    monkeypatch.setenv("FABRICATOR_MANAGED_MEMORY_GB", "5")
    reg = _make_registry(tmp_path)
    monkeypatch.setattr(reg, "_resolve_java_exec", lambda s: "managed-java")

    server = {"id": "srv_x", "memory": 2}  # no launch -> legacy default
    cmd = reg._build_command(server)
    assert cmd == ["managed-java", "-Xms5G", "-Xmx5G", "-jar", "server.jar", "nogui"]


def test_managed_args_file_pins_heap_before_argfile(tmp_path, monkeypatch):
    """A1 true-argv: the pin lands in its NORMAL slot before @args_file and the
    record jvm_args are dropped. Asserts the argv only (see module docstring for
    the accepted residual — an argfile-embedded -Xmx still wins in argv order)."""
    monkeypatch.setenv("FABRICATOR_MANAGED", "1")
    monkeypatch.setenv("FABRICATOR_MANAGED_MEMORY_GB", "8")
    reg = _make_registry(tmp_path)
    monkeypatch.setattr(reg, "_resolve_java_exec", lambda s: "managed-java")

    server = {
        "id": "srv_n",
        "memory": 3,
        "launch": {
            "type": "args_file",
            "args_file": "libraries/net/neoforged/neoforge/21.1.228/unix_args.txt",
            "jvm_args": ["-Xmx99G"],
            "program_args": ["nogui"],
        },
    }
    cmd = reg._build_command(server)
    assert cmd == [
        "managed-java",
        "-Xms8G",
        "-Xmx8G",
        "@libraries/net/neoforged/neoforge/21.1.228/unix_args.txt",
        "nogui",
    ]


def test_managed_fail_closed_when_memory_unset(tmp_path, monkeypatch):
    """Managed on + FABRICATOR_MANAGED_MEMORY_GB unset -> refuse to build."""
    import pytest

    from backend.managed import ManagedConfigError

    monkeypatch.setenv("FABRICATOR_MANAGED", "1")
    monkeypatch.delenv("FABRICATOR_MANAGED_MEMORY_GB", raising=False)
    reg = _make_registry(tmp_path)
    monkeypatch.setattr(reg, "_resolve_java_exec", lambda s: "managed-java")

    server = {"id": "srv_x", "memory": 4, "launch": {"type": "jar", "jar": "server.jar", "jvm_args": [], "program_args": ["nogui"]}}
    with pytest.raises(ManagedConfigError):
        reg._build_command(server)


def test_managed_fail_closed_when_memory_invalid(tmp_path, monkeypatch):
    """Managed on + a non-positive-int GB value -> refuse (never fall back)."""
    import pytest

    from backend.managed import ManagedConfigError

    monkeypatch.setenv("FABRICATOR_MANAGED", "1")
    monkeypatch.setenv("FABRICATOR_MANAGED_MEMORY_GB", "0")
    reg = _make_registry(tmp_path)
    monkeypatch.setattr(reg, "_resolve_java_exec", lambda s: "managed-java")

    server = {"id": "srv_x", "memory": 4}
    with pytest.raises(ManagedConfigError):
        reg._build_command(server)


def test_start_server_maps_managed_config_error_to_stopped(tmp_path, monkeypatch):
    """A3: start_server catches the fail-closed ManagedConfigError and returns
    the clean stopped shape — no exception bubbles up to a 500."""
    from backend.managed import ManagedConfigError

    reg = _make_registry(tmp_path)

    def _boom(_server):
        raise ManagedConfigError(
            "managed mode is on but FABRICATOR_MANAGED_MEMORY_GB is unset"
        )

    monkeypatch.setattr(reg, "_build_command", _boom)

    server = {"id": "srv_x", "status": "stopped", "installPath": "srv_x"}
    result = reg.start_server(server)
    assert result.get("status") == "stopped"
    assert "MANAGED_MEMORY_GB" in result.get("message", "")
