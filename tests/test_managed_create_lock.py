"""C1 — managed cap-1 create lock.

Managed-on, POST /api/servers succeeds only while ZERO server records exist
(the one legitimate first-boot bootstrap create); any further create is 403.
Off-flag, creation is unrestricted (regression pin).
"""
from __future__ import annotations


def _payload(port, name, path):
    return {
        "name": name,
        "version": "1.21.4",
        "loader": "paper",
        "port": port,
        "installPath": path,
    }


def test_managed_allows_first_create_when_empty(client, monkeypatch):
    monkeypatch.setenv("FABRICATOR_MANAGED", "1")
    resp = client.post("/api/servers", json=_payload(25811, "only", "only"))
    assert resp.status_code in (200, 201), resp.get_json()


def test_managed_locks_create_once_a_record_exists(client, monkeypatch):
    monkeypatch.setenv("FABRICATOR_MANAGED", "1")
    # zero records -> the single bootstrap create is allowed
    assert client.post("/api/servers", json=_payload(25812, "a", "a")).status_code in (200, 201)
    # a record now exists -> managed locks further creates
    resp = client.post("/api/servers", json=_payload(25813, "b", "b"))
    assert resp.status_code == 403
    assert "managed" in resp.get_json().get("error", "").lower()


def test_managed_lock_precedes_body_validation(client, monkeypatch):
    monkeypatch.setenv("FABRICATOR_MANAGED", "1")
    assert client.post("/api/servers", json=_payload(25814, "a", "a")).status_code in (200, 201)
    # an empty body would normally 400; the managed lock must 403 first
    resp = client.post("/api/servers", json={})
    assert resp.status_code == 403


def test_unmanaged_create_is_unrestricted(client, monkeypatch):
    monkeypatch.delenv("FABRICATOR_MANAGED", raising=False)
    assert client.post("/api/servers", json=_payload(25815, "a", "a")).status_code in (200, 201)
    resp = client.post("/api/servers", json=_payload(25816, "b", "b"))
    assert resp.status_code in (200, 201), resp.get_json()
