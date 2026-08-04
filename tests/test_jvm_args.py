"""Per-server Java runtime + launch flags (issue #54).

The launch builder already honoured `javaPath` and `launch.jvm_args`, but there
was no way to set them after creation, so the reporter resorted to renaming a
managed JDK directory to force a version and hand-editing files in the server
directory to pass flags.

`jvmArgs` is a new user-owned field kept deliberately separate from
`launch.jvm_args`, which installers own and rewrite. These tests pin that
separation, the precedence between them, and the two-speed validation: strict
on write, tolerant on the launch-builder read path (which also serves the
server-detail probe, where raising would turn a page load into a 500).
"""
from __future__ import annotations

import importlib
import sys

import pytest

from backend.server import jvm_args
from backend.server.jvm_args import JvmArgsError


@pytest.fixture(autouse=True)
def _fresh_modules():
    """Re-bind against what sys.modules holds NOW — test_app_factory.py purges
    every `backend.*` module. Same idiom as test_playit_provision.py."""
    global jvm_args, JvmArgsError
    jvm_args = importlib.import_module("backend.server.jvm_args")
    JvmArgsError = jvm_args.JvmArgsError


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def test_empty_input_yields_no_args():
    for value in (None, "", "   "):
        assert jvm_args.validate_jvm_args(value) == []


def test_splits_like_a_shell():
    assert jvm_args.validate_jvm_args("-XX:+UseZGC  -XX:+ZGenerational") == [
        "-XX:+UseZGC", "-XX:+ZGenerational"
    ]


def test_respects_quoting():
    """A -D value with a space is one argument, not two."""
    assert jvm_args.validate_jvm_args('-Dsome.prop="a b" -XX:+UseG1GC') == [
        "-Dsome.prop=a b", "-XX:+UseG1GC"
    ]


def test_multi_token_flags_survive():
    """--add-opens takes a following value token that has no leading dash; a
    naive 'every token must start with -' rule would reject it."""
    assert jvm_args.validate_jvm_args(
        "--add-opens java.base/java.lang=ALL-UNNAMED"
    ) == ["--add-opens", "java.base/java.lang=ALL-UNNAMED"]


def test_accepts_a_pre_tokenized_list():
    assert jvm_args.validate_jvm_args(["-XX:+UseZGC"]) == ["-XX:+UseZGC"]


def test_unbalanced_quotes_are_rejected():
    with pytest.raises(JvmArgsError, match="Could not parse"):
        jvm_args.validate_jvm_args('-Dfoo="unterminated')


def test_non_string_is_rejected():
    with pytest.raises(JvmArgsError, match="must be a string"):
        jvm_args.validate_jvm_args(42)


# ---------------------------------------------------------------------------
# Refused arguments
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("arg", ["-Xmx8G", "-Xms2G", "-XX:MaxHeapSize=8g"])
def test_heap_flags_are_refused(arg):
    """Heap belongs to the Memory setting. Accepting a second -Xmx would let it
    win silently and make that field a lie."""
    with pytest.raises(JvmArgsError, match="Memory setting"):
        jvm_args.validate_jvm_args(arg)


@pytest.mark.parametrize("arg", ["-jar", "-cp", "-classpath", "--class-path"])
def test_launch_selecting_flags_are_refused(arg):
    with pytest.raises(JvmArgsError, match="installer set up"):
        jvm_args.validate_jvm_args(f"{arg} other.jar")


def test_argument_files_are_refused():
    """@file is how NeoForge's own launch works; a user one would fight it."""
    with pytest.raises(JvmArgsError, match="argument files"):
        jvm_args.validate_jvm_args("@user_jvm_args.txt")


def test_oversized_input_is_refused():
    with pytest.raises(JvmArgsError, match="too long"):
        jvm_args.validate_jvm_args("-Dx=1 " * 500)


def test_too_many_args_refused():
    with pytest.raises(JvmArgsError, match="Too many"):
        jvm_args.validate_jvm_args(" ".join(f"-Dprop{i}=1" for i in range(65)))


# ---------------------------------------------------------------------------
# Tolerant parse (launch-builder path)
# ---------------------------------------------------------------------------

def test_parse_never_raises_on_a_corrupt_record(caplog):
    """Reached by the server-detail probe as well as start; an exception here
    would 500 a page load over a hand-edited field."""
    with caplog.at_level("WARNING"):
        assert jvm_args.parse_jvm_args('-Dfoo="unterminated', server_id="srv_x") == []
    assert "srv_x" in caplog.text


def test_parse_returns_valid_args():
    assert jvm_args.parse_jvm_args("-XX:+UseZGC") == ["-XX:+UseZGC"]


# ---------------------------------------------------------------------------
# javaPath validation
# ---------------------------------------------------------------------------

def test_java_path_accepts_a_bare_command():
    """Resolved on PATH at launch, so it cannot be checked here."""
    assert jvm_args.validate_java_path("java") == "java"
    assert jvm_args.validate_java_path("java21") == "java21"


def test_java_path_accepts_a_real_executable():
    assert jvm_args.validate_java_path(sys.executable) == sys.executable


def test_java_path_rejects_a_missing_file(tmp_path):
    with pytest.raises(JvmArgsError, match="No such java executable"):
        jvm_args.validate_java_path(str(tmp_path / "nope" / "java"))


def test_java_path_rejects_a_directory(tmp_path):
    """The likeliest mistake: pasting the JDK root instead of bin/java."""
    with pytest.raises(JvmArgsError, match="directory"):
        jvm_args.validate_java_path(str(tmp_path))


def test_java_path_rejects_a_non_executable(tmp_path):
    target = tmp_path / "java"
    target.write_text("#!/bin/sh\n")
    target.chmod(0o644)
    with pytest.raises(JvmArgsError, match="Not executable"):
        jvm_args.validate_java_path(str(target))


def test_java_path_empty_clears_the_override():
    for value in (None, "", "   "):
        assert jvm_args.validate_java_path(value) == ""


# ---------------------------------------------------------------------------
# Launch command assembly
# ---------------------------------------------------------------------------

def _registry(tmp_path):
    from backend.server.registry import ServerProcessRegistry
    return ServerProcessRegistry(str(tmp_path))


def _server(**overrides):
    server = {
        "id": "srv_1",
        "version": "1.21.4",
        "memory": 4,
        "memoryUnit": "GB",
        "javaPath": "/usr/bin/java",   # pinned so the command is deterministic
        "launch": {"type": "jar", "jar": "server.jar", "jvm_args": []},
    }
    server.update(overrides)
    return server


def test_user_args_land_before_the_jar(tmp_path):
    command = _registry(tmp_path)._build_command(
        _server(jvmArgs="-XX:+UseZGC -XX:+ZGenerational")
    )
    assert command == [
        "/usr/bin/java", "-Xms4G", "-Xmx4G",
        "-XX:+UseZGC", "-XX:+ZGenerational",
        "-jar", "server.jar", "nogui",
    ]


def test_user_args_come_after_installer_args(tmp_path):
    """Last occurrence wins in the JVM, so this ordering is what lets a user
    override an installer default instead of being overridden by it."""
    server = _server(
        jvmArgs="-XX:MaxGCPauseMillis=130",
        launch={"type": "jar", "jar": "server.jar",
                "jvm_args": ["-XX:MaxGCPauseMillis=200"]},
    )
    command = _registry(tmp_path)._build_command(server)
    installer_idx = command.index("-XX:MaxGCPauseMillis=200")
    user_idx = command.index("-XX:MaxGCPauseMillis=130")
    assert installer_idx < user_idx < command.index("-jar")


def test_user_args_apply_to_args_file_launches(tmp_path):
    """NeoForge launches via @args_file; flags must precede it."""
    server = _server(
        jvmArgs="-XX:+UseZGC",
        launch={"type": "args_file", "args_file": "user_jvm_args.txt", "jvm_args": []},
    )
    command = _registry(tmp_path)._build_command(server)
    assert command.index("-XX:+UseZGC") < command.index("@user_jvm_args.txt")


def test_user_args_apply_to_legacy_records(tmp_path):
    """Records predating LaunchSpec have no `launch` at all."""
    server = _server(jvmArgs="-XX:+UseZGC")
    server.pop("launch")
    command = _registry(tmp_path)._build_command(server)
    assert command == [
        "/usr/bin/java", "-Xms4G", "-Xmx4G", "-XX:+UseZGC",
        "-jar", "server.jar", "nogui",
    ]


def test_no_user_args_leaves_the_command_unchanged(tmp_path):
    """Regression guard: servers without the field must build exactly as before."""
    registry = _registry(tmp_path)
    assert registry._build_command(_server()) == registry._build_command(
        _server(jvmArgs="")
    )


def test_corrupt_user_args_are_dropped_not_fatal(tmp_path):
    command = _registry(tmp_path)._build_command(_server(jvmArgs='-Dfoo="oops'))
    assert command == [
        "/usr/bin/java", "-Xms4G", "-Xmx4G", "-jar", "server.jar", "nogui",
    ]


def test_managed_mode_strips_user_args(tmp_path, monkeypatch):
    """The deployment owns the JVM under managed mode; a tenant must not be able
    to hand it flags, exactly as with javaPath."""
    monkeypatch.setenv("FABRICATOR_MANAGED", "1")
    monkeypatch.setenv("FABRICATOR_MANAGED_MEMORY_GB", "6")
    command = _registry(tmp_path)._build_command(
        _server(jvmArgs="-XX:+UseZGC -XX:ActiveProcessorCount=32")
    )
    assert "-XX:+UseZGC" not in command
    assert "-XX:ActiveProcessorCount=32" not in command
    assert "-Xmx6G" in command


# ---------------------------------------------------------------------------
# Settings route
# ---------------------------------------------------------------------------

def _make_server(app, tmp_servers_root, port, path):
    from backend.server import storage

    with app.app_context():
        server = storage.create_server({
            "name": path,
            "version": "1.21.4",
            "loader": "fabric",
            "port": port,
            "installPath": path,
        })
    (tmp_servers_root / "servers" / path).mkdir(parents=True, exist_ok=True)
    return server["id"]


def test_settings_accepts_and_persists_jvm_args(client, app, tmp_servers_root):
    sid = _make_server(app, tmp_servers_root, 25921, "jvm-a")
    resp = client.put(f"/api/servers/{sid}/settings", json={"jvmArgs": "-XX:+UseZGC"})
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["jvmArgs"] == "-XX:+UseZGC"


def test_settings_rejects_heap_flags_with_a_useful_message(client, app, tmp_servers_root):
    sid = _make_server(app, tmp_servers_root, 25922, "jvm-b")
    resp = client.put(f"/api/servers/{sid}/settings", json={"jvmArgs": "-Xmx16G"})
    assert resp.status_code == 400
    assert "Memory setting" in resp.get_json()["error"]


def test_settings_rejects_a_bogus_java_path(client, app, tmp_servers_root):
    """Caught on write; otherwise it only surfaces as a server that won't start."""
    sid = _make_server(app, tmp_servers_root, 25923, "jvm-c")
    resp = client.put(
        f"/api/servers/{sid}/settings", json={"javaPath": "/no/such/java"}
    )
    assert resp.status_code == 400
    assert "No such java executable" in resp.get_json()["error"]


def test_settings_clears_the_override_with_an_empty_value(client, app, tmp_servers_root):
    sid = _make_server(app, tmp_servers_root, 25924, "jvm-d")
    client.put(f"/api/servers/{sid}/settings", json={"javaPath": sys.executable})
    resp = client.put(f"/api/servers/{sid}/settings", json={"javaPath": "   "})
    assert resp.status_code == 200
    assert resp.get_json()["javaPath"] == ""


def test_create_validates_java_path_too(client, tmp_servers_root):
    """The create modal offers javaPath; an unvalidated value there would build
    a server that installs fine and then refuses to start."""
    resp = client.post("/api/servers", json={
        "name": "bad-java", "version": "1.21.4", "loader": "fabric",
        "port": 25925, "installPath": "bad-java", "javaPath": "/no/such/java",
    })
    assert resp.status_code == 400
    assert "No such java executable" in resp.get_json()["error"]
