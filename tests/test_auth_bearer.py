"""The MCP bearer-token clause in the auth gate.

Exclusive resolution: an Authorization: Bearer header is a token request and
never falls back to the session. Fail-closed on the switch, the token, and the
route bucket. The clause sits below the DISABLE_AUTH opt-out and above the
public allowlist + session check.
"""
from __future__ import annotations

import pytest

from backend.auth import service

_READ_ROUTE = "/api/servers"
_MANAGE_ROUTE = "/api/servers/nope/start"
_NEVER_ROUTE = "/api/servers/nope/console"


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


# --- token accepted, within scope ------------------------------------------- #

def test_read_token_reaches_read_route(auth_client):
    service.set_mcp_enabled(True)
    tok = service.create_token("t", "read")["token"]
    assert auth_client.get(_READ_ROUTE, headers=_bearer(tok)).status_code == 200


def test_manage_token_reaches_read_route(auth_client):
    # manage ⊇ read
    service.set_mcp_enabled(True)
    tok = service.create_token("t", "manage")["token"]
    assert auth_client.get(_READ_ROUTE, headers=_bearer(tok)).status_code == 200


def test_manage_token_passes_gate_on_manage_route(auth_client):
    service.set_mcp_enabled(True)
    tok = service.create_token("t", "manage")["token"]
    resp = auth_client.post(_MANAGE_ROUTE, headers=_bearer(tok))
    # The gate lets it through to the handler (which 404s on the missing server).
    assert resp.status_code not in (401, 403)


# --- token rejected by scope / bucket --------------------------------------- #

def test_read_token_denied_on_manage_route(auth_client):
    service.set_mcp_enabled(True)
    tok = service.create_token("t", "read")["token"]
    resp = auth_client.post(_MANAGE_ROUTE, headers=_bearer(tok))
    assert resp.status_code == 403
    assert resp.get_json()["error"] == "insufficient scope"


@pytest.mark.parametrize("scope", ["read", "manage"])
def test_token_denied_on_never_route(auth_client, scope):
    service.set_mcp_enabled(True)
    tok = service.create_token("t", scope)["token"]
    resp = auth_client.post(_NEVER_ROUTE, headers=_bearer(tok))
    assert resp.status_code == 403
    assert resp.get_json()["error"] == "forbidden for token"


# --- token / switch authentication failures (401) --------------------------- #

def test_invalid_token_401(auth_client):
    service.set_mcp_enabled(True)
    resp = auth_client.get(_READ_ROUTE, headers=_bearer("fab_deadbeef_wrong"))
    assert resp.status_code == 401
    assert resp.get_json()["error"] == "invalid token"


def test_switch_off_rejects_valid_token(auth_client):
    tok = service.create_token("t", "read")["token"]  # switch left OFF
    resp = auth_client.get(_READ_ROUTE, headers=_bearer(tok))
    assert resp.status_code == 401
    assert resp.get_json()["error"] == "mcp token auth disabled"


# --- exclusive resolution: never fall back to a valid session --------------- #

def test_invalid_bearer_does_not_fall_back_to_session(authed_client):
    # SECURITY: authed_client carries a valid session cookie; an invalid bearer
    # token must still 401, not be rescued by the cookie.
    service.set_mcp_enabled(True)
    # Positive control: the SAME client + route with NO bearer header is 200, so
    # the 401 below cannot be a broken-session-fixture false positive.
    assert authed_client.get(_READ_ROUTE).status_code == 200
    resp = authed_client.get(_READ_ROUTE, headers=_bearer("fab_deadbeef_wrong"))
    assert resp.status_code == 401


def test_bearer_scheme_is_case_insensitive(authed_client):
    service.set_mcp_enabled(True)
    # Positive control: the SAME client + route with NO bearer header is 200.
    assert authed_client.get(_READ_ROUTE).status_code == 200
    resp = authed_client.get(
        _READ_ROUTE, headers={"Authorization": "bearer fab_deadbeef_wrong"}
    )
    assert resp.status_code == 401  # 'bearer' is still a token request, not session


def test_empty_bearer_is_rejected(authed_client):
    service.set_mcp_enabled(True)
    resp = authed_client.get(_READ_ROUTE, headers={"Authorization": "Bearer"})
    assert resp.status_code == 401  # present-but-empty is a rejected token request


# --- no-bearer requests are unchanged --------------------------------------- #

def test_non_bearer_scheme_uses_session(authed_client):
    resp = authed_client.get(_READ_ROUTE, headers={"Authorization": "Basic Zm9v"})
    assert resp.status_code == 200  # scheme ignored, session used as today


def test_non_bearer_scheme_without_session_still_401(auth_client):
    resp = auth_client.get(_READ_ROUTE, headers={"Authorization": "Basic Zm9v"})
    assert resp.status_code == 401  # not treated as a token, no session -> 401


def test_no_bearer_header_session_path_unchanged(authed_client):
    # No Authorization header at all: the session path is byte-identical to today.
    assert authed_client.get(_READ_ROUTE).status_code == 200


def test_setup_mode_bearer_is_rejected(setup_client):
    resp = setup_client.get(_READ_ROUTE, headers=_bearer("fab_deadbeef_wrong"))
    assert resp.status_code == 401
    assert resp.get_json()["error"] == "setup required"


# --- A1: prove the clause does NOT EXECUTE under DISABLE_AUTH ---------------- #

def test_disable_auth_never_runs_the_bearer_clause(client, monkeypatch):
    """SECURITY: with auth disabled the token path must not run at all.

    The DISABLE_AUTH short-circuit sits above the bearer clause, so mcp_state
    (the token path's fresh read) is never reached. Prove NON-EXECUTION, not
    just the outcome: make mcp_state explode, then a request carrying a bearer
    header must still 200 — a 500 would mean the clause ran (e.g. if it were
    ever moved above the DISABLE_AUTH opt-out).
    """
    def _boom(*args, **kwargs):
        raise AssertionError("token path executed under DISABLE_AUTH")

    monkeypatch.setattr(service, "mcp_state", _boom)
    # tmp_servers_root (via the client fixture) already sets DISABLE_AUTH=1.
    assert client.get(_READ_ROUTE, headers=_bearer("fab_looks_valid")).status_code == 200
    # Belt: a syntactically broken token must also pass straight through.
    assert client.get(_READ_ROUTE, headers=_bearer("not-a-token")).status_code == 200


# --- last-used is recorded on accepted requests, not on rejected ones -------- #

def _last_used(token_id):
    return next(t["last_used_at"] for t in service.list_tokens() if t["id"] == token_id)


def test_accepted_request_records_last_used(auth_client):
    service.set_mcp_enabled(True)
    tok = service.create_token("t", "read")
    assert _last_used(tok["id"]) is None
    assert auth_client.get(_READ_ROUTE, headers=_bearer(tok["token"])).status_code == 200
    assert _last_used(tok["id"]) is not None


def test_authorized_but_handler_404_still_records(auth_client):
    # Records AUTHORIZED use, not successful use: a manage token that passes the
    # gate and then 404s (missing server) still updates last_used_at.
    service.set_mcp_enabled(True)
    tok = service.create_token("t", "manage")
    resp = auth_client.post(_MANAGE_ROUTE, headers=_bearer(tok["token"]))
    assert resp.status_code not in (401, 403)  # gate authorized; handler 404s
    assert _last_used(tok["id"]) is not None


def test_rejected_invalid_token_records_nothing(auth_client):
    service.set_mcp_enabled(True)
    tok = service.create_token("t", "read")
    assert auth_client.get(
        _READ_ROUTE, headers=_bearer("fab_deadbeef_wrong")
    ).status_code == 401
    assert _last_used(tok["id"]) is None


def test_rejected_switch_off_records_nothing(auth_client):
    tok = service.create_token("t", "read")  # switch left OFF
    assert auth_client.get(_READ_ROUTE, headers=_bearer(tok["token"])).status_code == 401
    assert _last_used(tok["id"]) is None


def test_rejected_never_route_records_nothing(auth_client):
    service.set_mcp_enabled(True)
    tok = service.create_token("t", "read")
    assert auth_client.post(_NEVER_ROUTE, headers=_bearer(tok["token"])).status_code == 403
    assert _last_used(tok["id"]) is None


def test_rejected_insufficient_scope_records_nothing(auth_client):
    service.set_mcp_enabled(True)
    tok = service.create_token("t", "read")
    assert auth_client.post(_MANAGE_ROUTE, headers=_bearer(tok["token"])).status_code == 403
    assert _last_used(tok["id"]) is None
