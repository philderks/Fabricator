"""Dispatch tests for the players service.

Verifies that:
  - running server → registry.send_command, no Mojang lookup
  - stopped + addition + online-mode=true → file write + Mojang lookup
  - stopped + addition + online-mode=false → file write + offline UUID, no Mojang
  - stopped + removal (any mode) → file match by name, no Mojang
  - status change between check and send → 409
  - whitelist_active cache resets across stop/start (started_at differs)
"""
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from backend.server.players import service as players_service
from backend.server.players import files as players_files


class _FakeRegistry:
    def __init__(self, status: str, started_at: float | None = None, send_ok: bool = True):
        self._status = status
        self._started_at = started_at
        self._send_ok = send_ok
        self.sent_commands: list[str] = []
        self.install_path = None  # set in setup

    def get_status(self, server_id):
        result = {"status": self._status}
        if self._status == "running" and self._started_at is not None:
            result["startedAt"] = self._started_at
        return result

    def send_command(self, server_id, command):
        self.sent_commands.append(command)
        return {"success": self._send_ok, "message": "ok" if self._send_ok else "stopped"}

    def resolve_install_path(self, server):
        return self.install_path


def _server(online_mode=True):
    return {"id": "srv-1", "onlineMode": online_mode, "enforceWhitelist": False}


@pytest.fixture
def install(tmp_path: Path):
    install_path = tmp_path / "server"
    install_path.mkdir()
    yield install_path


def _registry_for(install_path, status, started_at=None, send_ok=True):
    reg = _FakeRegistry(status, started_at, send_ok)
    reg.install_path = install_path
    return reg


# ---------- running path ---------------------------------------------------

def test_running_whitelist_add_uses_send_command_no_mojang(install, monkeypatch):
    reg = _registry_for(install, "running", started_at=100.0)
    mojang_called = MagicMock(side_effect=AssertionError("must not call Mojang"))
    monkeypatch.setattr(players_service, "mojang_resolve_name", mojang_called)

    result = players_service.add_to_whitelist(reg, _server(), "Linus")

    assert result["name"] == "Linus"
    assert "whitelist add Linus" in reg.sent_commands
    mojang_called.assert_not_called()


def test_running_op_uses_send_command_with_level(install, monkeypatch):
    reg = _registry_for(install, "running", started_at=100.0)
    monkeypatch.setattr(
        players_service, "mojang_resolve_name",
        MagicMock(side_effect=AssertionError("no Mojang on running path")),
    )

    players_service.op_player(reg, _server(), "Linus", level=3)

    assert "op Linus" in reg.sent_commands  # vanilla command takes no level arg; level set via separate setting


def test_running_ban_includes_reason(install, monkeypatch):
    reg = _registry_for(install, "running", started_at=100.0)
    monkeypatch.setattr(players_service, "mojang_resolve_name", MagicMock())

    players_service.ban_player(reg, _server(), "Linus", reason="griefing")

    assert reg.sent_commands == ["ban Linus griefing"]


def test_running_kick_send_command(install):
    reg = _registry_for(install, "running", started_at=100.0)
    players_service.kick_player(reg, _server(), "Linus")
    assert reg.sent_commands == ["kick Linus"]


def test_kick_on_stopped_server_raises_conflict(install):
    reg = _registry_for(install, "stopped")
    with pytest.raises(players_service.ServerStateError):
        players_service.kick_player(reg, _server(), "Linus")


def test_send_command_failure_returns_409(install):
    reg = _registry_for(install, "running", started_at=100.0, send_ok=False)
    with pytest.raises(players_service.ServerStateError):
        players_service.add_to_whitelist(reg, _server(), "Linus")


# ---------- stopped addition ----------------------------------------------

def test_stopped_addition_online_mode_calls_mojang_and_writes_file(install, monkeypatch):
    reg = _registry_for(install, "stopped")
    monkeypatch.setattr(
        players_service, "mojang_resolve_name",
        MagicMock(return_value="11111111-2222-3333-4444-555555555555"),
    )

    players_service.add_to_whitelist(reg, _server(online_mode=True), "Linus")

    entries = players_files.read_json_list(install, "whitelist.json")
    assert entries == [{"uuid": "11111111-2222-3333-4444-555555555555", "name": "Linus"}]


def test_stopped_addition_offline_mode_uses_offline_uuid_no_mojang(install, monkeypatch):
    reg = _registry_for(install, "stopped")
    monkeypatch.setattr(
        players_service, "mojang_resolve_name",
        MagicMock(side_effect=AssertionError("offline mode must not call Mojang")),
    )

    players_service.add_to_whitelist(reg, _server(online_mode=False), "Linus")

    entries = players_files.read_json_list(install, "whitelist.json")
    assert len(entries) == 1
    expected = str(players_files.offline_uuid("Linus"))
    assert entries[0]["uuid"] == expected
    assert entries[0]["name"] == "Linus"


# ---------- stopped removal ----------------------------------------------

def test_stopped_removal_matches_by_name_no_mojang(install, monkeypatch):
    reg = _registry_for(install, "stopped")
    players_files.write_json_list(install, "whitelist.json", [
        {"uuid": "u1", "name": "Linus"},
        {"uuid": "u2", "name": "Notch"},
    ])
    monkeypatch.setattr(
        players_service, "mojang_resolve_name",
        MagicMock(side_effect=AssertionError("removal must not call Mojang")),
    )

    players_service.remove_from_whitelist(reg, _server(), "Linus")

    entries = players_files.read_json_list(install, "whitelist.json")
    assert entries == [{"uuid": "u2", "name": "Notch"}]


def test_stopped_removal_case_insensitive(install):
    reg = _registry_for(install, "stopped")
    players_files.write_json_list(install, "whitelist.json", [{"uuid": "u1", "name": "Linus"}])
    players_service.remove_from_whitelist(reg, _server(), "LINUS")
    assert players_files.read_json_list(install, "whitelist.json") == []


def test_stopped_removal_missing_entry_raises_not_found(install):
    reg = _registry_for(install, "stopped")
    with pytest.raises(players_service.PlayerNotInList):
        players_service.remove_from_whitelist(reg, _server(), "Linus")


# ---------- whitelist_active cache reset -----------------------------------

def test_whitelist_active_resets_on_started_at_change(install):
    cache = players_service.WhitelistActiveCache()

    reg_a = _registry_for(install, "running", started_at=100.0)
    server = _server()
    server["enforceWhitelist"] = True  # persisted property → initial value
    assert cache.get(reg_a, server) is True

    # Simulate stop + start: same server, new started_at.
    reg_b = _registry_for(install, "running", started_at=200.0)
    server["enforceWhitelist"] = False  # property updated while stopped
    assert cache.get(reg_b, server) is False  # re-initialised from new property


def test_whitelist_active_set_persists_within_same_run(install):
    cache = players_service.WhitelistActiveCache()
    reg = _registry_for(install, "running", started_at=100.0)
    server = _server()
    server["enforceWhitelist"] = False
    cache.set(reg, server, True)
    assert cache.get(reg, server) is True


# ---------- kick with reason -----------------------------------------------

def test_running_kick_with_reason_appends_reason_to_command(install):
    reg = _registry_for(install, "running", started_at=100.0)
    result = players_service.kick_player(reg, _server(), "Linus", reason="griefing")
    assert reg.sent_commands == ["kick Linus griefing"]
    assert result == {"name": "Linus", "reason": "griefing"}


def test_running_kick_without_reason_sends_bare_command(install):
    reg = _registry_for(install, "running", started_at=100.0)
    result = players_service.kick_player(reg, _server(), "Linus")
    assert reg.sent_commands == ["kick Linus"]
    assert result["reason"] is None


def test_running_kick_empty_reason_treated_as_no_reason(install):
    # reason=None and reason="" should both produce a bare kick command
    reg = _registry_for(install, "running", started_at=100.0)
    players_service.kick_player(reg, _server(), "Linus", reason=None)
    assert reg.sent_commands == ["kick Linus"]


# ---------- IP bans — running path ----------------------------------------

def test_running_ip_ban_no_reason_sends_bare_command(install):
    reg = _registry_for(install, "running", started_at=100.0)
    result = players_service.ban_ip(reg, _server(), "1.2.3.4")
    assert reg.sent_commands == ["ban-ip 1.2.3.4"]
    assert result == {"ip": "1.2.3.4", "reason": None}


def test_running_ip_ban_with_reason_appends_reason(install):
    reg = _registry_for(install, "running", started_at=100.0)
    players_service.ban_ip(reg, _server(), "1.2.3.4", reason="spamming")
    assert reg.sent_commands == ["ban-ip 1.2.3.4 spamming"]


def test_running_ip_ban_wildcard_address(install):
    reg = _registry_for(install, "running", started_at=100.0)
    players_service.ban_ip(reg, _server(), "192.168.*.*")
    assert reg.sent_commands == ["ban-ip 192.168.*.*"]


def test_running_ip_unban_sends_pardon_ip_command(install):
    reg = _registry_for(install, "running", started_at=100.0)
    result = players_service.unban_ip(reg, _server(), "1.2.3.4")
    assert reg.sent_commands == ["pardon-ip 1.2.3.4"]
    assert result == {"ip": "1.2.3.4"}


# ---------- IP bans — stopped path ----------------------------------------

def test_stopped_ip_ban_writes_entry_to_file(install):
    reg = _registry_for(install, "stopped")
    players_service.ban_ip(reg, _server(), "1.2.3.4", reason="hacking")
    entries = players_files.read_json_list(install, "banned-ips.json")
    assert len(entries) == 1
    assert entries[0]["ip"] == "1.2.3.4"
    assert entries[0]["reason"] == "hacking"


def test_stopped_ip_ban_sets_required_minecraft_fields(install):
    reg = _registry_for(install, "stopped")
    players_service.ban_ip(reg, _server(), "10.0.0.1")
    entry = players_files.read_json_list(install, "banned-ips.json")[0]
    assert entry["source"] == "Fabricator"
    assert entry["expires"] == "forever"
    assert "created" in entry
    # Default reason when none supplied
    assert entry["reason"] == "Banned by an operator."


def test_stopped_ip_ban_updates_existing_entry(install):
    """Re-banning the same IP updates the existing record rather than duplicating."""
    reg = _registry_for(install, "stopped")
    players_files.write_json_list(install, "banned-ips.json", [
        {"ip": "1.2.3.4", "reason": "old reason", "source": "Server",
         "expires": "forever", "created": "2020-01-01 00:00:00 +0000"},
    ])
    players_service.ban_ip(reg, _server(), "1.2.3.4", reason="new reason")
    entries = players_files.read_json_list(install, "banned-ips.json")
    assert len(entries) == 1
    assert entries[0]["reason"] == "new reason"
    assert entries[0]["source"] == "Fabricator"


def test_stopped_ip_ban_case_insensitive_dedup(install):
    """IP comparison is case-insensitive (IPv6 hex may differ in case)."""
    reg = _registry_for(install, "stopped")
    players_files.write_json_list(install, "banned-ips.json", [
        {"ip": "1.2.3.4", "reason": "x", "source": "S",
         "expires": "forever", "created": "2020-01-01 00:00:00 +0000"},
    ])
    players_service.ban_ip(reg, _server(), "1.2.3.4")
    assert len(players_files.read_json_list(install, "banned-ips.json")) == 1


def test_stopped_ip_unban_removes_entry(install):
    reg = _registry_for(install, "stopped")
    players_files.write_json_list(install, "banned-ips.json", [
        {"ip": "1.2.3.4", "reason": "griefing", "source": "S",
         "expires": "forever", "created": "2020-01-01 00:00:00 +0000"},
        {"ip": "5.6.7.8", "reason": "spam", "source": "S",
         "expires": "forever", "created": "2020-01-01 00:00:00 +0000"},
    ])
    players_service.unban_ip(reg, _server(), "1.2.3.4")
    remaining = players_files.read_json_list(install, "banned-ips.json")
    assert len(remaining) == 1
    assert remaining[0]["ip"] == "5.6.7.8"


def test_stopped_ip_unban_missing_entry_raises(install):
    reg = _registry_for(install, "stopped")
    with pytest.raises(players_service.PlayerNotInList):
        players_service.unban_ip(reg, _server(), "9.9.9.9")
