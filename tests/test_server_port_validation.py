"""Port coercion + duplicate detection on create and settings.

Two defects are pinned here:

* A non-numeric ``port`` used to reach a bare ``int()`` and surface as an
  unhandled 500. It is caller error, so it must be a 400.
* The stored port type was whatever the caller sent. The duplicate check
  compares the requested port against every stored record, and
  ``"25565" == 25565`` is False in Python — so one string-typed record made
  the panel happily put a second server on a port already in use.
"""
from __future__ import annotations

import json


def _payload(port, name, path):
    return {
        "name": name,
        "version": "1.21.4",
        "loader": "paper",
        "port": port,
        "installPath": path,
    }


def _created(client, port, name, path):
    resp = client.post("/api/servers", json=_payload(port, name, path))
    assert resp.status_code in (200, 201), resp.get_json()
    return resp.get_json()


# --------------------------------------------------------------------------- #
# Create
# --------------------------------------------------------------------------- #

def test_non_numeric_port_is_a_400_not_a_500(client):
    resp = client.post("/api/servers", json=_payload("not-a-port", "bad", "bad"))
    assert resp.status_code == 400, resp.get_json()
    assert "port" in resp.get_json().get("error", "").lower()


def test_null_port_is_a_400(client):
    resp = client.post("/api/servers", json=_payload(None, "bad", "bad2"))
    assert resp.status_code == 400, resp.get_json()


def test_boolean_port_is_rejected(client):
    """``int(True)`` is 1, so a JSON ``true`` would otherwise pass as port 1."""
    resp = client.post("/api/servers", json=_payload(True, "bad", "bad3"))
    assert resp.status_code == 400, resp.get_json()


def test_out_of_range_ports_are_rejected(client):
    for port in (0, -1, 70000):
        resp = client.post("/api/servers", json=_payload(port, f"p{port}", f"p{port}"))
        assert resp.status_code == 400, (port, resp.get_json())


def test_numeric_string_port_is_stored_as_int(client):
    """The stored type must be int — that is what keeps the duplicate check honest."""
    created = _created(client, "25820", "strport", "strport")
    assert created["port"] == 25820
    assert isinstance(created["port"], int)


def test_duplicate_port_is_rejected(client):
    _created(client, 25821, "first", "first")
    resp = client.post("/api/servers", json=_payload(25821, "second", "second"))
    assert resp.status_code == 400
    assert "already in use" in resp.get_json().get("error", "").lower()


def test_duplicate_port_detected_against_a_legacy_string_record(
    client, tmp_servers_root
):
    """A record written by an older build may hold a string port. The check
    coerces both sides, so it still collides instead of double-booking."""
    index = tmp_servers_root / "servers.json"
    index.write_text(
        json.dumps([
            {
                "id": "srv_legacy",
                "name": "legacy",
                "version": "1.21.4",
                "loader": "paper",
                "port": "25822",          # legacy string port
                "installPath": "legacy",
                "status": "stopped",
            }
        ]),
        encoding="utf-8",
    )

    resp = client.post("/api/servers", json=_payload(25822, "clash", "clash"))
    assert resp.status_code == 400, resp.get_json()
    assert "already in use" in resp.get_json().get("error", "").lower()


def test_a_corrupt_port_on_another_record_does_not_block_creates(
    client, tmp_servers_root
):
    """An unparseable stored port cannot bind anything, so it must not be
    treated as a conflict for every subsequent create."""
    index = tmp_servers_root / "servers.json"
    index.write_text(
        json.dumps([
            {
                "id": "srv_corrupt",
                "name": "corrupt",
                "version": "1.21.4",
                "loader": "paper",
                "port": "garbage",
                "installPath": "corrupt",
                "status": "stopped",
            }
        ]),
        encoding="utf-8",
    )

    resp = client.post("/api/servers", json=_payload(25823, "fine", "fine"))
    assert resp.status_code in (200, 201), resp.get_json()


# --------------------------------------------------------------------------- #
# Settings
# --------------------------------------------------------------------------- #

def test_settings_rejects_a_non_numeric_port(client):
    created = _created(client, 25824, "settings", "settings")
    resp = client.put(
        f"/api/servers/{created['id']}/settings", json={"port": "nope"}
    )
    assert resp.status_code == 400, resp.get_json()


def test_settings_stores_a_numeric_string_port_as_int(client):
    created = _created(client, 25825, "settings2", "settings2")
    resp = client.put(
        f"/api/servers/{created['id']}/settings", json={"port": "25826"}
    )
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["port"] == 25826


def test_settings_cannot_take_another_servers_port(client):
    first = _created(client, 25827, "one", "one")
    second = _created(client, 25828, "two", "two")
    resp = client.put(
        f"/api/servers/{second['id']}/settings", json={"port": first["port"]}
    )
    assert resp.status_code == 400, resp.get_json()
    assert "already in use" in resp.get_json().get("error", "").lower()


def test_settings_may_keep_its_own_port(client):
    """The duplicate check must exclude the record being edited, or every
    settings save that leaves the port alone would fail."""
    created = _created(client, 25829, "self", "self")
    resp = client.put(
        f"/api/servers/{created['id']}/settings",
        json={"port": 25829, "motd": "unchanged port"},
    )
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["port"] == 25829
