"""HTTP-surface tests for the player-management routes added in this sprint.

Covers:
  - _patch_server_property helper (unit, no Flask required)
  - PATCH /players/whitelist/enforce — stopped-server persisted toggle
  - POST/DELETE /players/bans/ip — IP ban endpoints
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from backend.server.players.routes import _patch_server_property
from backend.utils.time import iso_z_from_timestamp


# ---------------------------------------------------------------------------
# Helpers shared by route tests
# ---------------------------------------------------------------------------

def _seed_server(tmp_root: Path, server_id: str, extra: dict | None = None) -> Path:
    """Write a stopped server record to servers.json and return its install path."""
    record = {
        "id": server_id,
        "name": "Test",
        "version": "1.20.4",
        "loader": "vanilla",
        "port": 25565,
        "installPath": server_id,   # relative → resolved under servers_root
        "status": "stopped",
        "onlineMode": True,
        "enforceWhitelist": False,
    }
    if extra:
        record.update(extra)

    index = tmp_root / "servers.json"
    existing = json.loads(index.read_text()) if index.exists() else []
    existing.append(record)
    index.write_text(json.dumps(existing), encoding="utf-8")

    install = tmp_root / "servers" / server_id
    install.mkdir(parents=True, exist_ok=True)
    return install


# ---------------------------------------------------------------------------
# _patch_server_property unit tests
# ---------------------------------------------------------------------------

def test_patch_updates_existing_key(tmp_path):
    props = tmp_path / "server.properties"
    props.write_text("motd=hello\nenforce-whitelist=false\nonline-mode=true\n")
    _patch_server_property(tmp_path, "enforce-whitelist", True)
    lines = props.read_text().splitlines()
    assert "enforce-whitelist=true" in lines
    # Other lines untouched
    assert any("motd=hello" in l for l in lines)
    assert any("online-mode=true" in l for l in lines)


def test_patch_appends_missing_key(tmp_path):
    props = tmp_path / "server.properties"
    props.write_text("motd=hello\n")
    _patch_server_property(tmp_path, "enforce-whitelist", False)
    content = props.read_text()
    assert "enforce-whitelist=false" in content
    assert "motd=hello" in content  # original preserved


def test_patch_bool_true_writes_lowercase_true(tmp_path):
    props = tmp_path / "server.properties"
    props.write_text("enforce-whitelist=false\n")
    _patch_server_property(tmp_path, "enforce-whitelist", True)
    assert "enforce-whitelist=true" in props.read_text()


def test_patch_bool_false_writes_lowercase_false(tmp_path):
    props = tmp_path / "server.properties"
    props.write_text("enforce-whitelist=true\n")
    _patch_server_property(tmp_path, "enforce-whitelist", False)
    assert "enforce-whitelist=false" in props.read_text()


def test_patch_does_nothing_when_file_missing(tmp_path):
    # No server.properties at all — function should not raise.
    _patch_server_property(tmp_path, "enforce-whitelist", True)
    assert not (tmp_path / "server.properties").exists()


def test_patch_only_replaces_exact_key_not_partial_match(tmp_path):
    props = tmp_path / "server.properties"
    props.write_text("enforce-whitelist=false\nwhite-list=false\n")
    _patch_server_property(tmp_path, "enforce-whitelist", True)
    lines = props.read_text().splitlines()
    assert "enforce-whitelist=true" in lines
    assert "white-list=false" in lines  # must not be touched


# ---------------------------------------------------------------------------
# GET /servers/<id>/players/state — knownPlayers[].lastSeen (issue #49)
# ---------------------------------------------------------------------------

def test_state_known_player_last_seen_from_playerdata(client, tmp_servers_root):
    """knownPlayers carries a lastSeen sourced from the playerdata mtime, not
    the usercache expiresOn."""
    install = _seed_server(Path(tmp_servers_root), "srv_lastseen")
    uuid = "11111111-2222-3333-4444-555555555555"
    mtime = 1_600_000_000

    from backend.server.players import files as players_files
    players_files.write_json_list(install, "usercache.json", [
        {"uuid": uuid, "name": "Linus", "expiresOn": "2099-01-01 00:00:00 +0000"},
    ])
    pd = install / "world" / "playerdata"
    pd.mkdir(parents=True, exist_ok=True)
    dat = pd / f"{uuid}.dat"
    dat.write_bytes(b"NBT")
    os.utime(dat, (mtime, mtime))

    resp = client.get("/api/servers/srv_lastseen/players/state")
    assert resp.status_code == 200
    known = resp.get_json()["knownPlayers"]
    assert len(known) == 1
    assert known[0]["lastSeen"] == iso_z_from_timestamp(mtime)


def test_state_known_player_last_seen_from_new_players_data_layout(client, tmp_servers_root):
    """26.1+ world layout: the per-player file lives at
    <level>/players/data/<uuid>.dat — the probing resolver must find it."""
    install = _seed_server(Path(tmp_servers_root), "srv_newlayout")
    uuid = "22222222-3333-4444-5555-666666666666"
    mtime = 1_610_000_000

    from backend.server.players import files as players_files
    players_files.write_json_list(install, "usercache.json", [
        {"uuid": uuid, "name": "Newlayout"},
    ])
    pd = install / "world" / "players" / "data"
    pd.mkdir(parents=True, exist_ok=True)
    dat = pd / f"{uuid}.dat"
    dat.write_bytes(b"NBT")
    os.utime(dat, (mtime, mtime))

    resp = client.get("/api/servers/srv_newlayout/players/state")
    assert resp.status_code == 200
    known = resp.get_json()["knownPlayers"]
    assert known[0]["lastSeen"] == iso_z_from_timestamp(mtime)


def test_state_known_player_last_seen_null_when_never_joined(client, tmp_servers_root):
    """A player in usercache with no playerdata file reports lastSeen: null."""
    install = _seed_server(Path(tmp_servers_root), "srv_neverjoined")
    from backend.server.players import files as players_files
    players_files.write_json_list(install, "usercache.json", [
        {"uuid": "99999999-8888-7777-6666-555555555555", "name": "Ghost"},
    ])

    resp = client.get("/api/servers/srv_neverjoined/players/state")
    assert resp.status_code == 200
    known = resp.get_json()["knownPlayers"]
    assert known[0]["lastSeen"] is None


# ---------------------------------------------------------------------------
# PATCH /servers/<id>/players/whitelist/enforce
# ---------------------------------------------------------------------------

def test_enforce_whitelist_updates_storage_and_properties(client, tmp_servers_root):
    install = _seed_server(Path(tmp_servers_root), "srv_enforce")
    (install / "server.properties").write_text("enforce-whitelist=false\n")

    resp = client.patch(
        "/api/servers/srv_enforce/players/whitelist/enforce",
        json={"active": True},
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert resp.get_json()["enforceWhitelist"] is True

    # server.properties on disk reflects the change
    content = (install / "server.properties").read_text()
    assert "enforce-whitelist=true" in content

    # Storage record is also updated
    from backend.server import storage
    server = storage.get_server("srv_enforce")
    assert server["enforceWhitelist"] is True


def test_enforce_whitelist_can_be_turned_off(client, tmp_servers_root):
    install = _seed_server(
        Path(tmp_servers_root), "srv_enforce_off",
        extra={"enforceWhitelist": True},
    )
    (install / "server.properties").write_text("enforce-whitelist=true\n")

    resp = client.patch(
        "/api/servers/srv_enforce_off/players/whitelist/enforce",
        json={"active": False},
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert "enforce-whitelist=false" in (install / "server.properties").read_text()


def test_enforce_whitelist_running_server_returns_409(client, tmp_servers_root, monkeypatch):
    _seed_server(Path(tmp_servers_root), "srv_running")

    fake_reg = MagicMock()
    fake_reg.get_status.return_value = {"status": "running"}
    monkeypatch.setattr("backend.server.players.routes._registry", lambda: fake_reg)

    resp = client.patch(
        "/api/servers/srv_running/players/whitelist/enforce",
        json={"active": True},
        content_type="application/json",
    )
    assert resp.status_code == 409


def test_enforce_whitelist_unknown_server_returns_404(client, tmp_servers_root):
    resp = client.patch(
        "/api/servers/no_such_server/players/whitelist/enforce",
        json={"active": True},
        content_type="application/json",
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /servers/<id>/players/bans/ip
# ---------------------------------------------------------------------------

def test_ip_ban_post_writes_entry_to_file(client, tmp_servers_root):
    install = _seed_server(Path(tmp_servers_root), "srv_ipban")

    resp = client.post(
        "/api/servers/srv_ipban/players/bans/ip",
        json={"ip": "1.2.3.4", "reason": "cheating"},
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert resp.get_json()["ip"] == "1.2.3.4"

    from backend.server.players import files as players_files
    entries = players_files.read_json_list(install, "banned-ips.json")
    assert len(entries) == 1
    assert entries[0]["ip"] == "1.2.3.4"
    assert entries[0]["reason"] == "cheating"


def test_ip_ban_post_wildcard_ip_accepted(client, tmp_servers_root):
    _seed_server(Path(tmp_servers_root), "srv_ipwild")
    resp = client.post(
        "/api/servers/srv_ipwild/players/bans/ip",
        json={"ip": "192.168.*.*"},
        content_type="application/json",
    )
    assert resp.status_code == 200


def test_ip_ban_post_invalid_ip_returns_400(client, tmp_servers_root):
    _seed_server(Path(tmp_servers_root), "srv_badip")

    for bad in ("not-an-ip", "1.2.3", "1.2.3.4.5", "", "1.2.3.256"):
        resp = client.post(
            "/api/servers/srv_badip/players/bans/ip",
            json={"ip": bad},
            content_type="application/json",
        )
        assert resp.status_code == 400, f"Expected 400 for ip={bad!r}, got {resp.status_code}"


def test_ip_ban_post_invalid_reason_returns_400(client, tmp_servers_root):
    _seed_server(Path(tmp_servers_root), "srv_badreason")
    resp = client.post(
        "/api/servers/srv_badreason/players/bans/ip",
        json={"ip": "1.2.3.4", "reason": "bad\nreason"},
        content_type="application/json",
    )
    assert resp.status_code == 400


def test_ip_ban_post_running_uses_command(client, tmp_servers_root, monkeypatch):
    install = _seed_server(Path(tmp_servers_root), "srv_iprun")
    sent = []

    fake_reg = MagicMock()
    fake_reg.get_status.return_value = {"status": "running"}
    fake_reg.send_command.side_effect = lambda sid, cmd: (sent.append(cmd), {"success": True})[1]
    fake_reg.resolve_install_path.return_value = install
    monkeypatch.setattr("backend.server.players.routes._registry", lambda: fake_reg)

    resp = client.post(
        "/api/servers/srv_iprun/players/bans/ip",
        json={"ip": "1.2.3.4", "reason": "spamming"},
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert sent == ["ban-ip 1.2.3.4 spamming"]


# ---------------------------------------------------------------------------
# DELETE /servers/<id>/players/bans/ip
# ---------------------------------------------------------------------------

def test_ip_ban_delete_removes_entry(client, tmp_servers_root):
    install = _seed_server(Path(tmp_servers_root), "srv_ipdel")

    from backend.server.players import files as players_files
    players_files.write_json_list(install, "banned-ips.json", [
        {"ip": "1.2.3.4", "reason": "x", "source": "S",
         "expires": "forever", "created": "2020-01-01 00:00:00 +0000"},
    ])

    resp = client.delete(
        "/api/servers/srv_ipdel/players/bans/ip",
        json={"ip": "1.2.3.4"},
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert players_files.read_json_list(install, "banned-ips.json") == []


def test_ip_ban_delete_missing_entry_returns_404(client, tmp_servers_root):
    _seed_server(Path(tmp_servers_root), "srv_ipnotfound")
    resp = client.delete(
        "/api/servers/srv_ipnotfound/players/bans/ip",
        json={"ip": "9.9.9.9"},
        content_type="application/json",
    )
    assert resp.status_code == 404


def test_ip_ban_delete_invalid_ip_returns_400(client, tmp_servers_root):
    _seed_server(Path(tmp_servers_root), "srv_ipdelbad")
    resp = client.delete(
        "/api/servers/srv_ipdelbad/players/bans/ip",
        json={"ip": "not-valid"},
        content_type="application/json",
    )
    assert resp.status_code == 400
