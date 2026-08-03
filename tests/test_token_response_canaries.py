"""A token caller never receives a credential and never receives a host path.

That is the whole rule, and this test is the mechanism that keeps it true.

It is deliberately VALUE-based, not key-based. The redaction it guards works on
key NAMES; a test that also worked on key names would only prove the filter
agrees with itself. So instead we plant canary VALUES in every credential and
path field the route audit found one in, drive every token-reachable route from
the SAME table the enumeration test uses, and go RED if a canary value appears
anywhere in a response body -- at any nesting depth, in the success shape or the
error shape, under any key name.

RESIDUAL, stated plainly and not defined away: a genuinely new credential field
whose key the filter does not know AND whose value no fixture here plants is
undetected by both layers. Planting a value below is what closes that gap for
the next field; nothing here closes it automatically.

Routes this suite cannot drive offline are declared in ``_UNEXERCISED`` with the
reason each needs setup the test cannot provide. They are named, never silently
skipped, and a token-reachable route that is neither exercised nor declared
fails ``test_unexercised_routes_are_declared_and_current``.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.auth.buckets import BUCKETS

# Planted values. CANARY_PATH is a real directory-name segment, so every
# absolute path the app builds underneath it genuinely contains the canary.
CANARY_SECRET = "canary-rcon-secret-value"
CANARY_PATH = "canary-host-path-segment"
CANARIES = (CANARY_SECRET, CANARY_PATH)

_JAR = "canary-mod.jar"

# Token-reachable routes this suite cannot drive offline, each with the reason.
# Not skips: the coverage test below asserts every entry is still token-reachable,
# and anything token-reachable that is NOT listed here gets exercised by default,
# so a newly classified route is covered with no second edit.
_UNEXERCISED = {
    ("GET", "/api/modrinth/categories"): "live Modrinth API",
    ("GET", "/api/modrinth/game-versions"): "live Modrinth API",
    ("GET", "/api/modrinth/loaders"): "live Modrinth API",
    ("GET", "/api/modrinth/mod/<mod_id>"): "live Modrinth API",
    ("GET", "/api/modrinth/mod/<mod_id>/download-url"): "live Modrinth API",
    ("GET", "/api/modrinth/mod/<mod_id>/versions"): "live Modrinth API",
    ("GET", "/api/modrinth/modpacks/search"): "live Modrinth API",
    ("GET", "/api/modrinth/project/<project_id>"): "live Modrinth API",
    ("GET", "/api/modrinth/project/<project_id>/resolve-version"): "live Modrinth API",
    ("GET", "/api/modrinth/project/<project_id>/versions"): "live Modrinth API",
    ("GET", "/api/modrinth/search"): "live Modrinth API",
    ("GET", "/api/modrinth/version/<version_id>"): "live Modrinth API",
    ("POST", "/api/modrinth/mod/<mod_id>/install"): "live Modrinth API + a real download",
    ("GET", "/api/loaders/<loader>/versions/game"): "live loader/Mojang metadata API",
    ("GET", "/api/loaders/<loader>/versions/loader"): "live loader/Mojang metadata API",
    ("POST", "/api/servers/<server_id>/install"): "spawns an installer thread and downloads upstream",
}


def _token_reachable():
    return {key for key, bucket in BUCKETS.items() if bucket in ("read", "manage")}


@pytest.fixture
def canary(tmp_path, monkeypatch):
    """An auth-enabled app whose every root path carries the path canary."""
    root = tmp_path / CANARY_PATH
    servers_root = root / "servers"
    servers_root.mkdir(parents=True)

    monkeypatch.setenv("SERVER_ROOT", str(servers_root))
    monkeypatch.setenv("SERVER_INDEX_FILE", str(root / "servers.json"))
    monkeypatch.setenv("JAVA_ROOT", str(root / "java"))
    monkeypatch.setenv("BACKUPS_DIR", str(root / "backups"))
    monkeypatch.setenv("FLASK_ENV", "development")
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:3000")
    monkeypatch.setenv("HOST", "127.0.0.1")
    # The token path only exists when auth is on.
    monkeypatch.delenv("FABRICATOR_DISABLE_AUTH", raising=False)
    monkeypatch.setenv("SECRET_KEY", "test-secret-key")

    from backend.auth import service

    monkeypatch.setenv("FABRICATOR_AUTH_PASSWORD_HASH", service.hash_password("pw"))

    import backend.server.registry as registry_mod

    registry_mod.reset_for_tests()

    # start/stop/restart embed the server record in their responses (success AND
    # error shapes). Stub the process layer so those shapes are exercised without
    # spawning a JVM; _augment_with_runtime itself stays real.
    _stub = {"status": "stopped", "message": "stubbed"}
    monkeypatch.setattr(
        registry_mod.ServerProcessRegistry, "start_server",
        lambda self, server, **kw: dict(_stub),
    )
    monkeypatch.setattr(
        registry_mod.ServerProcessRegistry, "stop_server",
        lambda self, server_id: dict(_stub),
    )
    monkeypatch.setattr(
        registry_mod.ServerProcessRegistry, "restart_server",
        lambda self, server: {"stop": dict(_stub), "start": dict(_stub)},
    )

    from backend.core.app import create_app

    app = create_app()
    app.config["TESTING"] = True

    # --- plant the canaries -------------------------------------------------- #
    from backend.server import storage

    install_path = servers_root / "canary-server"
    (install_path / "mods").mkdir(parents=True)

    server = storage.create_server({
        "name": "canary",
        "version": "1.20.1",
        "loader": "vanilla",
        "installPath": str(install_path),                                  # path
        "javaPath": str(root / "java" / "21" / "bin" / "java.exe"),        # path
        "rconPassword": CANARY_SECRET,                                     # credential
        "enableRcon": True,
    })
    sid = server["id"]

    # java manager: a managed install whose absolute binary path is reported
    from backend.server.java_manager import java_binary

    jdk_bin = root / "java" / "21" / "bin"
    jdk_bin.mkdir(parents=True, exist_ok=True)
    (jdk_bin / java_binary(21)).write_text("stub")

    # backup config (storagePath) + snapshot (filePath)
    from backend.backups import storage as backups_storage

    config = backups_storage.create_config(sid, {
        "name": "canary-config",
        "storagePath": str(root / "backups" / "target"),
    })
    snapshot = backups_storage.record_snapshot(sid, {
        "configId": config["id"],
        "type": "backup",
        "fileName": "snap.tar.gz",
        "filePath": str(root / "backups" / "snap.tar.gz"),
        "sizeBytes": 1024,
    })

    service.set_mcp_enabled(True)
    token = service.create_token("canary", "manage")["token"]

    return SimpleNamespace(
        client=app.test_client(),
        token=token,
        sid=sid,
        config_id=config["id"],
        snapshot_id=snapshot["id"],
        mods_dir=install_path / "mods",
    )


def _concrete(rule: str, ctx) -> str:
    """Turn a Flask rule into a concrete path against the planted fixture."""
    values = {
        "<server_id>": ctx.sid,
        "<mod_id>": "sodium",
        "<project_id>": "sodium",
        "<version_id>": "abcd1234",
        "<task_id>": "canary-task",
        "<job_id>": "canary-job",
        "<config_id>": ctx.config_id,
        "<snapshot_id>": ctx.snapshot_id,
        "<loader>": "vanilla",
        "<path:filename>": _JAR,
    }
    path = rule
    for placeholder, value in values.items():
        path = path.replace(placeholder, str(value))
    return path


def _send(ctx, method: str, path: str):
    headers = {"Authorization": f"Bearer {ctx.token}"}
    if method == "DELETE" and path.endswith("/mods"):
        return ctx.client.delete(path, headers=headers, json={"filenames": [_JAR]})
    return ctx.client.open(path, method=method, headers=headers)


def test_no_canary_value_in_any_token_response(canary):
    leaks = {}
    for method, rule in sorted(_token_reachable()):
        if (method, rule) in _UNEXERCISED:
            continue
        # Re-plant per request: the mod-delete routes consume the jar.
        canary.mods_dir.mkdir(parents=True, exist_ok=True)
        (canary.mods_dir / _JAR).write_bytes(b"PK\x03\x04canary")

        response = _send(canary, method, _concrete(rule, canary))
        body = response.get_data(as_text=True)
        found = sorted(value for value in CANARIES if value in body)
        if found:
            leaks[f"{method} {rule}"] = (response.status_code, found)

    assert not leaks, "token responses leaked canary values:\n" + "\n".join(
        f"  {route} -> {status} {values}" for route, (status, values) in sorted(leaks.items())
    )


def test_unexercised_routes_are_declared_and_current():
    """The declared coverage gap must stay honest: no stale, no reasonless entries."""
    stale = sorted(set(_UNEXERCISED) - _token_reachable())
    assert not stale, f"_UNEXERCISED lists routes that are no longer token-reachable: {stale}"
    assert all(_UNEXERCISED.values()), "every unexercised route must carry a reason"
