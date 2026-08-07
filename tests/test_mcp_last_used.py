"""Recording token last-used: persistence, the per-token throttle, and the
guarantee that a flush never clobbers a concurrent password change nor
resurrects a revoked token.

These drive service.touch_token_last_used directly — no gate involvement.
"""
from __future__ import annotations

import json

import pytest

from backend.auth import service


@pytest.fixture(autouse=True)
def _reset_buffers():
    # The last-used buffers are module-level; isolate every test.
    service.reset_for_tests()
    yield
    service.reset_for_tests()


def _read(tmp):
    return json.loads((tmp / "auth.json").read_text(encoding="utf-8"))


def test_touch_records_last_used_on_first_use(tmp_servers_root):
    tok = service.create_token("t", "read")
    assert service.list_tokens()[0]["last_used_at"] is None
    service.touch_token_last_used(tok["id"])
    assert service.list_tokens()[0]["last_used_at"] is not None


# --- A2 T1/T2: mint <-> password change, both directions, both survive ------ #

def test_mint_then_change_password_both_survive(tmp_servers_root, monkeypatch):
    monkeypatch.delenv("FABRICATOR_AUTH_PASSWORD_HASH", raising=False)
    tok = service.create_token("t", "read")
    service.set_password("new-pw")
    assert service.verify_password("new-pw") is True
    assert service.match_token(service.mcp_state()["tokens"], tok["token"]) == (
        tok["id"],
        "read",
    )


def test_change_password_then_mint_both_survive(tmp_servers_root, monkeypatch):
    monkeypatch.delenv("FABRICATOR_AUTH_PASSWORD_HASH", raising=False)
    service.set_password("pw1")
    tok = service.create_token("t", "manage")
    assert service.verify_password("pw1") is True
    assert service.match_token(service.mcp_state()["tokens"], tok["token"]) == (
        tok["id"],
        "manage",
    )


# --- A2 T3: a pending flush must not clobber a new password_hash ------------ #

def test_pending_flush_does_not_clobber_password(tmp_servers_root, monkeypatch):
    monkeypatch.delenv("FABRICATOR_AUTH_PASSWORD_HASH", raising=False)
    clock = {"t": 1000.0}
    monkeypatch.setattr(service, "_now_monotonic", lambda: clock["t"])

    tok = service.create_token("t", "read")
    service.touch_token_last_used(tok["id"])   # first touch -> flushes
    service.touch_token_last_used(tok["id"])   # inside window -> buffered, pending
    service.set_password("pw-after")           # password changes with a flush pending
    clock["t"] += 61                           # window elapses
    service.touch_token_last_used(tok["id"])   # flushes the pending value

    assert service.verify_password("pw-after") is True
    data = _read(tmp_servers_root)
    assert data["password_hash"]                                     # survived the flush
    assert data["mcp"]["tokens"][tok["id"]]["last_used_at"] is not None


# --- A2 T4: a revoked token is not resurrected by a later flush -------------- #

def test_revoked_token_not_resurrected_by_flush(tmp_servers_root, monkeypatch):
    clock = {"t": 5000.0}
    monkeypatch.setattr(service, "_now_monotonic", lambda: clock["t"])

    tok = service.create_token("t", "read")
    service.touch_token_last_used(tok["id"])   # flush #1
    service.touch_token_last_used(tok["id"])   # buffered (pending), a stale entry
    assert service.revoke_token(tok["id"]) is True  # removed from file; buffer still holds it
    clock["t"] += 61
    service.touch_token_last_used(tok["id"])   # triggers a flush; the stale id must drop

    data = _read(tmp_servers_root)
    assert tok["id"] not in data["mcp"]["tokens"]                    # not recreated
    assert service.match_token(service.mcp_state()["tokens"], tok["token"]) is None


# --- A2 T5: a flush persists only tokens still present in the file ----------- #

def test_flush_only_persists_present_tokens(tmp_servers_root):
    tok = service.create_token("a", "read")
    # Seed the write-side buffer with a present id and an absent (revoked) id,
    # then drive the flush directly.
    service._last_used_buffer[tok["id"]] = "2026-07-24T00:00:00.000000Z"
    service._last_used_buffer["absent-id"] = "2026-07-24T00:00:00.000000Z"
    with service._lock:
        flushed = service._flush_last_used_locked()

    assert flushed == {tok["id"]}                                   # only the present id
    data = _read(tmp_servers_root)
    assert data["mcp"]["tokens"][tok["id"]]["last_used_at"] == "2026-07-24T00:00:00.000000Z"
    assert "absent-id" not in data["mcp"]["tokens"]                 # never created
    assert service._last_used_buffer == {}                         # buffer drained


# --- A2 T6: throttle — <=1 write per token per window ------------------------ #

def test_throttle_at_most_one_write_per_window(tmp_servers_root, monkeypatch):
    clock = {"t": 100.0}
    monkeypatch.setattr(service, "_now_monotonic", lambda: clock["t"])

    tok = service.create_token("t", "read")

    writes = {"n": 0}
    real_write = service._write_auth_file

    def _spy(data):
        writes["n"] += 1
        return real_write(data)

    monkeypatch.setattr(service, "_write_auth_file", _spy)

    service.touch_token_last_used(tok["id"])   # first accepted use -> one write
    assert writes["n"] == 1
    service.touch_token_last_used(tok["id"])   # inside the window -> no write
    assert writes["n"] == 1
    clock["t"] += 61                           # window elapses
    service.touch_token_last_used(tok["id"])   # -> one more write
    assert writes["n"] == 2
