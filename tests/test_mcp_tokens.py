"""MCP API token generation, verification, revocation, and listing."""
from __future__ import annotations

import hashlib
import json

import pytest

from backend.auth import service


def test_create_and_match_round_trip(tmp_servers_root):
    created = service.create_token("My laptop", "read")
    assert created["scope"] == "read"
    assert created["token"].startswith("fab_")
    tokens = service.mcp_state()["tokens"]
    assert service.match_token(tokens, created["token"]) == (created["id"], "read")


def test_created_secret_is_only_the_hash_on_disk(tmp_servers_root):
    created = service.create_token("agent", "manage")
    secret = created["token"].split("_", 2)[2]
    data = json.loads((tmp_servers_root / "auth.json").read_text(encoding="utf-8"))
    entry = data["mcp"]["tokens"][created["id"]]
    # SECURITY: the plaintext secret is never persisted — only its sha256.
    assert "secret" not in entry
    assert entry["hash"] == hashlib.sha256(secret.encode("utf-8")).hexdigest()
    assert secret not in json.dumps(data)
    # list_tokens exposes metadata only, never the hash.
    listed = service.list_tokens()
    assert listed and all("hash" not in t and "token" not in t for t in listed)


def test_match_wrong_secret_returns_none(tmp_servers_root):
    created = service.create_token("t", "read")
    prefix, tid, secret = created["token"].split("_", 2)
    tampered = f"{prefix}_{tid}_{secret[:-1]}{'A' if secret[-1] != 'A' else 'B'}"
    assert service.match_token(service.mcp_state()["tokens"], tampered) is None


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "nope",
        "fab_only",
        "fab__",
        "fab_id_",
        "notfab_id_secret",
        "read_id_secret",
    ],
)
def test_match_malformed_returns_none(tmp_servers_root, bad):
    # A malformed credential must fail closed, never raise.
    service.create_token("t", "read")
    assert service.match_token(service.mcp_state()["tokens"], bad) is None


def test_match_unknown_id_returns_none(tmp_servers_root):
    service.create_token("t", "read")
    assert service.match_token(service.mcp_state()["tokens"], "fab_deadbeef_secret") is None


def test_revoke_removes_token(tmp_servers_root):
    created = service.create_token("t", "manage")
    assert service.revoke_token(created["id"]) is True
    assert service.match_token(service.mcp_state()["tokens"], created["token"]) is None
    assert service.revoke_token(created["id"]) is False  # already gone


def test_token_cap_enforced(tmp_servers_root):
    for i in range(service._MAX_TOKENS):
        service.create_token(f"tok {i}", "read")
    with pytest.raises(service.TokenLimitReached):
        service.create_token("one too many", "read")


@pytest.mark.parametrize("bad_name", ["", "   ", "a" * 65, "bad/name", "bad;name", "nl\nname"])
def test_invalid_name_rejected(tmp_servers_root, bad_name):
    with pytest.raises(ValueError):
        service.create_token(bad_name, "read")


@pytest.mark.parametrize("bad_scope", ["admin", "", "READ", "write", None])
def test_invalid_scope_rejected(tmp_servers_root, bad_scope):
    with pytest.raises(ValueError):
        service.create_token("t", bad_scope)


def test_list_tokens_oldest_first_metadata(tmp_servers_root):
    a = service.create_token("first", "read")
    b = service.create_token("second", "manage")
    listed = service.list_tokens()
    ids = [t["id"] for t in listed]
    assert set(ids) == {a["id"], b["id"]}
    assert listed[0]["last_used_at"] is None
    assert {t["scope"] for t in listed} == {"read", "manage"}
