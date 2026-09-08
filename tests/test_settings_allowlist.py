"""PUT /servers/<id>/settings writes only actual settings.

The route used to merge whatever JSON it received into the stored record,
stripping just `id` and `createdAt`. That made panel bookkeeping — the
installed-content manifest, the modpack record, the persisted status, the
installer-derived launch spec — writable by any session client, so a
read-modify-write client bug could silently corrupt it.

Also pins the allowlist against drift: it is derived from what
``_build_server_properties`` reads and what the settings form owns, and a new
field added to either without updating the allowlist would be silently
unwritable (the settings form would appear to save and change nothing).
"""
from __future__ import annotations

import inspect
import re

from backend.server import routes as server_routes


def _make_server(app, tmp_servers_root, port, path):
    from backend.server import storage

    with app.app_context():
        server = storage.create_server({
            "name": path,
            "version": "1.21.4",
            "loader": "paper",
            "port": port,
            "installPath": path,
        })
    (tmp_servers_root / "servers" / path).mkdir(parents=True, exist_ok=True)
    return server["id"]


# --------------------------------------------------------------------------- #
# Bookkeeping fields are refused
# --------------------------------------------------------------------------- #

def test_internal_bookkeeping_fields_are_refused(client, app, tmp_servers_root):
    """Each of these is panel state, not a setting. None is sent by any real
    client, and writing any of them corrupts something the panel relies on."""
    sid = _make_server(app, tmp_servers_root, 25931, "bk")

    for field, value in [
        ("modContent", {"evil.jar": {"projectId": "x"}}),
        ("modpack", {"name": "spoofed"}),
        ("pendingModpack", {"projectId": "x"}),
        ("status", "running"),
        ("launch", {"type": "jar"}),
        ("command", "java -jar evil.jar"),
        ("version", "1.99.9"),
        ("loader", "forge"),
        ("installPath", "/etc"),
        ("autoStart", "always"),
    ]:
        resp = client.put(f"/api/servers/{sid}/settings", json={field: value})
        assert resp.status_code == 400, (field, resp.get_json())
        assert field in resp.get_json().get("error", ""), field


def test_refusal_names_every_offending_field(client, app, tmp_servers_root):
    sid = _make_server(app, tmp_servers_root, 25932, "names")
    resp = client.put(
        f"/api/servers/{sid}/settings",
        json={"motd": "fine", "status": "running", "modContent": {}},
    )
    assert resp.status_code == 400
    body = resp.get_json()
    assert set(body["unsettable_fields"]) == {"status", "modContent"}


def test_a_refused_write_changes_nothing(client, app, tmp_servers_root):
    """The rejection must happen before the merge — a partially-applied write
    would be worse than either accepting or refusing outright."""
    from backend.server import storage

    sid = _make_server(app, tmp_servers_root, 25933, "atomic")
    with app.app_context():
        storage.update_server(sid, {"modContent": {"real.jar": {"projectId": "keep"}}})

    resp = client.put(
        f"/api/servers/{sid}/settings",
        json={"motd": "should not land", "modContent": {}},
    )
    assert resp.status_code == 400

    with app.app_context():
        record = storage.get_server(sid)
    assert record["modContent"] == {"real.jar": {"projectId": "keep"}}
    assert record.get("motd") != "should not land"


def test_status_cannot_be_forced(client, app, tmp_servers_root):
    """Writing status directly would desync the record from the process
    registry — the panel would show 'running' with no JVM behind it."""
    from backend.server import storage

    sid = _make_server(app, tmp_servers_root, 25934, "status")
    resp = client.put(f"/api/servers/{sid}/settings", json={"status": "running"})
    assert resp.status_code == 400

    with app.app_context():
        assert storage.get_server(sid)["status"] != "running"


# --------------------------------------------------------------------------- #
# Real settings still work
# --------------------------------------------------------------------------- #

def test_ordinary_settings_still_save(client, app, tmp_servers_root):
    sid = _make_server(app, tmp_servers_root, 25935, "ok")
    resp = client.put(
        f"/api/servers/{sid}/settings",
        json={"motd": "Hello", "difficulty": "hard", "maxPlayers": 30, "memory": 6},
    )
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    assert body["motd"] == "Hello"
    assert body["difficulty"] == "hard"
    assert body["maxPlayers"] == 30


def test_the_full_ui_payload_is_accepted(client, app, tmp_servers_root):
    """Every settable field at once — the shape the settings form actually
    submits. A missing allowlist entry shows up here as a 400."""
    sid = _make_server(app, tmp_servers_root, 25936, "full")
    payload = {field: _sample_value(field) for field in server_routes.SETTABLE_SETTINGS_FIELDS}
    payload["port"] = 25936  # keep its own port; a different one may collide
    resp = client.put(f"/api/servers/{sid}/settings", json=payload)
    assert resp.status_code == 200, resp.get_json()


def _sample_value(field: str):
    """A type-plausible value for one settings field."""
    if field in {"javaPath", "jvmArgs"}:
        return ""  # empty clears the override; any path would have to exist
    if field == "memoryUnit":
        return "GB"
    if field == "difficulty":
        return "normal"
    if field == "gamemode":
        return "survival"
    if field in {"memory", "maxPlayers", "port", "queryPort", "rconPort"}:
        return 25936 if field.endswith("ort") else 4
    return "x"


def test_server_generated_echo_fields_are_ignored_not_refused(
    client, app, tmp_servers_root
):
    """A read-modify-write client (GET the server, tweak one field, PUT it back)
    echoes fields the server itself produced. Those carry no intent to change
    anything, so they are dropped rather than turned into a 400."""
    sid = _make_server(app, tmp_servers_root, 25937, "echo")
    fetched = client.get(f"/api/servers/{sid}").get_json()

    payload = {
        key: value for key, value in fetched.items()
        if key in server_routes.SETTABLE_SETTINGS_FIELDS
        or key in server_routes._SETTINGS_IGNORED_ECHO_FIELDS
    }
    payload["motd"] = "Round tripped"

    resp = client.put(f"/api/servers/{sid}/settings", json=payload)
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["motd"] == "Round tripped"
    assert resp.get_json()["id"] == sid  # id echoed back, never overwritten


def test_id_and_created_at_cannot_be_overwritten(client, app, tmp_servers_root):
    from backend.server import storage

    sid = _make_server(app, tmp_servers_root, 25938, "ident")
    with app.app_context():
        created_at = storage.get_server(sid)["createdAt"]

    resp = client.put(
        f"/api/servers/{sid}/settings",
        json={"id": "srv_hijack", "createdAt": "1999-01-01T00:00:00Z", "motd": "m"},
    )
    assert resp.status_code == 200, resp.get_json()

    with app.app_context():
        record = storage.get_server(sid)
    assert record["id"] == sid
    assert record["createdAt"] == created_at


# --------------------------------------------------------------------------- #
# Drift pin
# --------------------------------------------------------------------------- #

def test_allowlist_covers_every_server_properties_field():
    """``_build_server_properties`` is the definition of a server.properties
    setting. A field it reads that the allowlist omits is silently unwritable:
    the form would appear to save and the value would never change."""
    source = inspect.getsource(server_routes._build_server_properties)
    read_fields = set(re.findall(r"server\.get\('(\w+)'", source))

    missing = read_fields - server_routes.SETTABLE_SETTINGS_FIELDS
    assert not missing, (
        "server.properties fields missing from SETTABLE_SETTINGS_FIELDS "
        f"(they would be silently unwritable): {sorted(missing)}"
    )


def test_allowlist_has_no_fields_the_record_does_not_use():
    """The reverse direction: an allowlist entry that is neither a
    server.properties field nor known record-level tuning is dead weight, and
    dead weight in a security boundary is how the boundary rots."""
    source = inspect.getsource(server_routes._build_server_properties)
    read_fields = set(re.findall(r"server\.get\('(\w+)'", source))

    unexplained = (
        server_routes.SETTABLE_SETTINGS_FIELDS
        - read_fields
        - server_routes._SETTINGS_RECORD_FIELDS
    )
    assert not unexplained, sorted(unexplained)


def test_every_field_the_settings_form_submits_is_settable():
    """Cross-branch contract (cf. CC5 / test_runtime_status_pin).

    The settings form submits ``defaultSettings()`` from the Pinia store
    wholesale. A field added there but not to the allowlist makes the whole save
    fail with a 400 — not just that field — so this parses the store and checks
    the real payload shape rather than trusting the backend constant.
    """
    from pathlib import Path

    store = (
        Path(__file__).resolve().parents[1]
        / "frontend" / "src" / "stores" / "server.js"
    )
    assert store.is_file(), f"settings store not found at {store}"

    source = store.read_text(encoding="utf-8")
    marker = "const defaultSettings = (data = {}) => ({"
    assert marker in source, (
        "Could not find defaultSettings() in the store — this cross-branch pin "
        "needs updating to match the new shape."
    )
    block = source.split(marker, 1)[1].split("\n  })", 1)[0]
    submitted = set(re.findall(r"^\s{4}(\w+):", block, re.M))

    assert len(submitted) > 50, (
        f"Parsed only {len(submitted)} keys from defaultSettings(); the parser "
        "in this test is probably stale rather than the store being tiny."
    )

    missing = submitted - server_routes.SETTABLE_SETTINGS_FIELDS
    assert not missing, (
        "The settings form submits fields the backend allowlist refuses, so "
        f"every settings save would 400: {sorted(missing)}. Add them to "
        "SETTABLE_SETTINGS_FIELDS in backend/server/routes.py."
    )


def test_bookkeeping_fields_are_absent_from_the_allowlist():
    """A belt-and-braces pin naming the fields that must never become settable,
    so re-adding one is a deliberate act with a failing test attached."""
    forbidden = {
        "id", "createdAt", "status", "launch", "command", "modContent",
        "modpack", "pendingModpack", "version", "loader", "installPath",
    }
    overlap = forbidden & server_routes.SETTABLE_SETTINGS_FIELDS
    assert not overlap, sorted(overlap)
