"""HTTP-surface tests for GET /api/servers/<id>/files/search.

Covers the happy path (recursive name match), the scoped search, path-traversal
rejection, and the truncation flag.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


def _seed_server(tmp_root: Path, server_id: str = "srv1") -> Path:
    """Write a stopped server record to servers.json and return its install path."""
    record = {
        "id": server_id,
        "name": "Test",
        "version": "1.20.4",
        "loader": "vanilla",
        "port": 25565,
        "installPath": server_id,   # relative → resolved under servers_root
        "status": "stopped",
    }
    index = tmp_root / "servers.json"
    existing = json.loads(index.read_text()) if index.exists() else []
    existing.append(record)
    index.write_text(json.dumps(existing), encoding="utf-8")

    install = tmp_root / "servers" / server_id
    install.mkdir(parents=True, exist_ok=True)
    return install


@pytest.fixture
def seeded(tmp_servers_root):
    install = _seed_server(tmp_servers_root)
    (install / "server.properties").write_text("motd=hi\n", encoding="utf-8")
    (install / "config").mkdir()
    (install / "config" / "mod.properties").write_text("a=1\n", encoding="utf-8")
    (install / "world").mkdir()
    (install / "world" / "level.dat").write_bytes(b"\x00")
    return install


def test_search_finds_matches_across_the_tree(client, seeded):
    resp = client.get("/api/servers/srv1/files/search?q=properties")
    assert resp.status_code == 200
    body = resp.get_json()

    paths = {entry["relativePath"] for entry in body["results"]}
    assert paths == {"server.properties", str(Path("config") / "mod.properties")}
    assert body["truncated"] is False

    by_name = {entry["name"]: entry for entry in body["results"]}
    assert by_name["mod.properties"]["parentPath"] == "config"
    assert by_name["server.properties"]["parentPath"] == ""
    assert by_name["server.properties"]["isDir"] is False


def test_search_is_case_insensitive_and_matches_directories(client, seeded):
    resp = client.get("/api/servers/srv1/files/search?q=WORLD")
    assert resp.status_code == 200
    results = resp.get_json()["results"]

    assert len(results) == 1
    assert results[0]["name"] == "world"
    assert results[0]["isDir"] is True
    # Directories skip the recursive size walk.
    assert results[0]["size"] is None


def test_search_can_be_scoped_to_a_subdirectory(client, seeded):
    resp = client.get("/api/servers/srv1/files/search?q=properties&path=config")
    assert resp.status_code == 200
    body = resp.get_json()

    assert body["scope"] == "config"
    assert [entry["name"] for entry in body["results"]] == ["mod.properties"]


def test_search_requires_a_query(client, seeded):
    resp = client.get("/api/servers/srv1/files/search?q=%20%20")
    assert resp.status_code == 400
    assert "q" in resp.get_json()["error"]


def test_search_rejects_path_traversal(client, seeded):
    resp = client.get("/api/servers/srv1/files/search?q=x&path=../..")
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "Invalid path"


def test_search_flags_truncated_results(client, seeded):
    for i in range(5):
        (seeded / f"match{i}.txt").write_text("x", encoding="utf-8")

    resp = client.get("/api/servers/srv1/files/search?q=match&limit=3")
    assert resp.status_code == 200
    body = resp.get_json()

    assert len(body["results"]) == 3
    assert body["truncated"] is True


def test_exact_limit_result_set_is_not_flagged_truncated(client, seeded):
    for i in range(3):
        (seeded / f"match{i}.txt").write_text("x", encoding="utf-8")

    resp = client.get("/api/servers/srv1/files/search?q=match&limit=3")
    body = resp.get_json()

    assert len(body["results"]) == 3
    assert body["truncated"] is False


def test_search_missing_scope_directory_is_404(client, seeded):
    resp = client.get("/api/servers/srv1/files/search?q=x&path=nope")
    assert resp.status_code == 404
