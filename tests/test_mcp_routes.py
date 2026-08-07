"""MCP integration management endpoints: the switch + API-token CRUD.

All four are session-gated and NEVER-bucketed (no token may reach them).
"""
from __future__ import annotations

import json

import pytest

from backend.auth import service

MCP = "/api/integrations/mcp"
TOKENS = "/api/integrations/mcp/tokens"

_ROUTES = [
    ("get", MCP),
    ("put", MCP),
    ("post", TOKENS),
    ("delete", TOKENS + "/whatever"),
]


# --- every route requires a session ----------------------------------------- #

@pytest.mark.parametrize("method,path", _ROUTES)
def test_routes_require_session(auth_client, method, path):
    assert getattr(auth_client, method)(path).status_code == 401


# --- no token may reach them (NEVER bucket), either scope -------------------- #

@pytest.mark.parametrize("scope", ["read", "manage"])
@pytest.mark.parametrize("method,path", _ROUTES)
def test_routes_reject_bearer_token(auth_client, scope, method, path):
    service.set_mcp_enabled(True)
    tok = service.create_token("t", scope)["token"]
    resp = getattr(auth_client, method)(path, headers={"Authorization": f"Bearer {tok}"})
    assert resp.status_code == 403


# --- GET: switch + metadata only, never a secret or hash -------------------- #

def test_get_returns_switch_and_metadata_no_secret(authed_client):
    authed_client.put(MCP, json={"enabled": True})
    created = authed_client.post(TOKENS, json={"name": "laptop", "scope": "read"}).get_json()
    body = authed_client.get(MCP).get_json()
    assert body["enabled"] is True
    assert len(body["tokens"]) == 1
    entry = body["tokens"][0]
    assert set(entry) == {"id", "name", "scope", "created_at", "last_used_at"}
    assert "hash" not in entry
    payload = json.dumps(body)
    assert "fab_" not in payload
    assert created["token"] not in payload


# --- POST: the secret appears exactly once ---------------------------------- #

def test_post_returns_secret_once(authed_client):
    created = authed_client.post(TOKENS, json={"name": "x", "scope": "manage"})
    assert created.status_code == 201
    body = created.get_json()
    assert body["token"].startswith("fab_")
    assert body["scope"] == "manage"
    # A later GET never shows the secret again.
    assert body["token"] not in json.dumps(authed_client.get(MCP).get_json())


# --- validation ------------------------------------------------------------- #

@pytest.mark.parametrize(
    "payload",
    [
        {"name": "", "scope": "read"},        # empty name
        {"name": "bad/name", "scope": "read"},  # bad charset
        {"name": "x", "scope": "admin"},       # unknown scope
        {"name": "x"},                          # missing scope
        {"scope": "read"},                      # missing name
        "not-a-json-object",                    # non-dict body
    ],
)
def test_post_bad_body_400(authed_client, payload):
    assert authed_client.post(TOKENS, json=payload).status_code == 400


@pytest.mark.parametrize("payload", [{"enabled": "yes"}, {"enabled": 1}, {}, {"enabled": None}])
def test_put_non_bool_400(authed_client, payload):
    assert authed_client.put(MCP, json=payload).status_code == 400


# --- cap -------------------------------------------------------------------- #

def test_cap_25_then_409(authed_client):
    for i in range(25):
        assert authed_client.post(TOKENS, json={"name": f"t{i}", "scope": "read"}).status_code == 201
    assert authed_client.post(TOKENS, json={"name": "extra", "scope": "read"}).status_code == 409


# --- delete ----------------------------------------------------------------- #

def test_delete_unknown_id_404(authed_client):
    assert authed_client.delete(TOKENS + "/does-not-exist").status_code == 404


def test_delete_existing_204_and_revokes_live(authed_client):
    authed_client.put(MCP, json={"enabled": True})
    created = authed_client.post(TOKENS, json={"name": "x", "scope": "read"}).get_json()
    hdr = {"Authorization": f"Bearer {created['token']}"}
    assert authed_client.get("/api/servers", headers=hdr).status_code == 200
    assert authed_client.delete(TOKENS + "/" + created["id"]).status_code == 204
    # revocation is live — no restart needed.
    assert authed_client.get("/api/servers", headers=hdr).status_code == 401


# --- rulings: mint while off, and off/on preserves tokens ------------------- #

def test_mint_allowed_while_switch_off_produces_inert_token(authed_client):
    # switch is OFF by default; minting is still allowed.
    created = authed_client.post(TOKENS, json={"name": "x", "scope": "read"})
    assert created.status_code == 201
    hdr = {"Authorization": f"Bearer {created.get_json()['token']}"}
    assert authed_client.get("/api/servers", headers=hdr).status_code == 401  # inert
    authed_client.put(MCP, json={"enabled": True})
    assert authed_client.get("/api/servers", headers=hdr).status_code == 200  # activated


def test_switch_off_then_on_preserves_tokens(authed_client):
    authed_client.put(MCP, json={"enabled": True})
    created = authed_client.post(TOKENS, json={"name": "x", "scope": "read"}).get_json()
    hdr = {"Authorization": f"Bearer {created['token']}"}
    assert authed_client.get("/api/servers", headers=hdr).status_code == 200
    authed_client.put(MCP, json={"enabled": False})
    assert authed_client.get("/api/servers", headers=hdr).status_code == 401     # rejected
    assert len(authed_client.get(MCP).get_json()["tokens"]) == 1                 # not deleted
    authed_client.put(MCP, json={"enabled": True})
    assert authed_client.get("/api/servers", headers=hdr).status_code == 200     # resolves again
