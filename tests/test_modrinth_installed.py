"""Hash-based identification of installed mods (issue #52).

The mods page used to identify jars by guessing project slugs from filenames:
every hyphen-prefix, longest first, one request each. That averaged ~3.6
requests per jar, so a 200-mod folder issued ~720 requests per page refresh
against Modrinth's 300/min per-IP budget.

These tests pin the replacement: hash the jars, ask `version_files` in bulk,
and cost a bounded number of requests regardless of folder size.
"""
from __future__ import annotations

import hashlib
import importlib
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from backend.modrinth import installed
from backend.modrinth.client import ModrinthApiError, ModrinthClient
from backend.modrinth.ratelimit import RateLimiter


@pytest.fixture(autouse=True)
def _fresh_modules():
    """Re-bind the module-level names against what sys.modules holds NOW.

    test_app_factory.py deletes every cached `backend.*` module, after which the
    imports above point at a stale copy — one whose module-global lookup caches
    the conftest reset fixture (which imports fresh) never clears. That leaks
    cached hashes between tests and makes assertions about request counts fail
    only in a full-suite run. Same idiom as test_playit_provision.py.
    """
    global installed, ModrinthApiError, ModrinthClient, RateLimiter
    installed = importlib.import_module("backend.modrinth.installed")
    client_mod = importlib.import_module("backend.modrinth.client")
    ModrinthApiError = client_mod.ModrinthApiError
    ModrinthClient = client_mod.ModrinthClient
    RateLimiter = importlib.import_module("backend.modrinth.ratelimit").RateLimiter
    installed.clear_caches()


def _write_jar(directory: Path, name: str, body: bytes) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_bytes(body)
    return path


def _sha1(body: bytes) -> str:
    return hashlib.sha1(body).hexdigest()


def _fake_client(versions=None, projects=None):
    """A client stub recording how many upstream calls each phase made."""
    client = MagicMock()
    client.get_versions_by_hashes.return_value = versions or {}
    client.get_projects.return_value = projects or []
    return client


# ---------------------------------------------------------------------------
# Hashing
# ---------------------------------------------------------------------------

def test_file_sha1_matches_hashlib(tmp_path):
    path = _write_jar(tmp_path, "a.jar", b"jar bytes")
    assert installed.file_sha1(path) == _sha1(b"jar bytes")


def test_file_sha1_is_cached_until_the_file_changes(tmp_path):
    path = _write_jar(tmp_path, "a.jar", b"one")
    assert installed.file_sha1(path) == _sha1(b"one")

    path.write_bytes(b"two")
    import os
    os.utime(path, (1, 1))  # distinct mtime even on a coarse clock
    assert installed.file_sha1(path) == _sha1(b"two")


def test_file_sha1_returns_none_for_unreadable(tmp_path):
    assert installed.file_sha1(tmp_path / "missing.jar") is None


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------

def test_resolves_filenames_to_project_metadata(tmp_path):
    jar = _write_jar(tmp_path, "some-renamed-file.jar", b"sodium bytes")
    digest = _sha1(b"sodium bytes")

    client = _fake_client(
        versions={digest: {"project_id": "AABBCCDD", "id": "vvv", "version_number": "0.6.0"}},
        projects=[{"id": "AABBCCDD", "slug": "sodium", "title": "Sodium",
                   "icon_url": "https://cdn/sodium.png"}],
    )

    resolved = installed.resolve_jar_files(client, [jar])

    assert resolved == {
        "some-renamed-file.jar": {
            "projectId": "AABBCCDD",
            "slug": "sodium",
            "title": "Sodium",
            "iconUrl": "https://cdn/sodium.png",
            "versionId": "vvv",
            "versionNumber": "0.6.0",
        }
    }


def test_identifies_a_jar_not_named_after_its_slug(tmp_path):
    """The old filename guesser could not resolve this at any prefix length;
    the hash does not care what the file is called."""
    jar = _write_jar(tmp_path, "totally-unrelated-name.jar", b"iris bytes")
    client = _fake_client(
        versions={_sha1(b"iris bytes"): {"project_id": "IRIS", "id": "v1", "version_number": "1.7"}},
        projects=[{"id": "IRIS", "slug": "iris", "title": "Iris Shaders"}],
    )

    resolved = installed.resolve_jar_files(client, [jar])
    assert resolved["totally-unrelated-name.jar"]["title"] == "Iris Shaders"


def test_a_whole_folder_costs_two_upstream_requests(tmp_path):
    """The core regression pin: request count must not scale with mod count."""
    jars = []
    versions = {}
    projects = []
    for i in range(150):
        body = f"mod-{i}".encode()
        jars.append(_write_jar(tmp_path, f"mod-{i}-fabric-1.2.3+mc1.21.jar", body))
        versions[_sha1(body)] = {"project_id": f"P{i}", "id": f"v{i}", "version_number": "1.2.3"}
        projects.append({"id": f"P{i}", "slug": f"mod-{i}", "title": f"Mod {i}"})

    client = _fake_client(versions=versions, projects=projects)
    resolved = installed.resolve_jar_files(client, jars)

    assert len(resolved) == 150
    assert client.get_versions_by_hashes.call_count == 1
    assert client.get_projects.call_count == 1


def test_unknown_jars_are_absent_not_guessed(tmp_path):
    """A jar Modrinth doesn't know is simply omitted — the caller decides what
    to render. It must never be attributed to some other project."""
    jar = _write_jar(tmp_path, "homemade.jar", b"custom")
    client = _fake_client(versions={}, projects=[])

    assert installed.resolve_jar_files(client, [jar]) == {}


def test_second_call_hits_no_api_at_all(tmp_path):
    """A page refresh — the exact trigger in the report — must be free."""
    jar = _write_jar(tmp_path, "a.jar", b"bytes")
    versions = {_sha1(b"bytes"): {"project_id": "P", "id": "v", "version_number": "1"}}
    projects = [{"id": "P", "slug": "p", "title": "P"}]

    first = _fake_client(versions, projects)
    installed.resolve_jar_files(first, [jar])

    second = _fake_client(versions, projects)
    resolved = installed.resolve_jar_files(second, [jar])

    assert resolved["a.jar"]["title"] == "P"
    second.get_versions_by_hashes.assert_not_called()
    second.get_projects.assert_not_called()


def test_negative_results_are_cached_too(tmp_path):
    """Unrecognised jars must not be re-queried on every load — that was a
    large share of the original 404 traffic."""
    jar = _write_jar(tmp_path, "homemade.jar", b"custom")

    first = _fake_client(versions={})
    installed.resolve_jar_files(first, [jar])
    assert first.get_versions_by_hashes.call_count == 1

    second = _fake_client(versions={})
    installed.resolve_jar_files(second, [jar])
    second.get_versions_by_hashes.assert_not_called()


def test_duplicate_jars_share_one_lookup(tmp_path):
    """Two copies of the same jar are one hash, and both get the metadata."""
    body = b"same bytes"
    a = _write_jar(tmp_path, "a.jar", body)
    b = _write_jar(tmp_path, "b.jar", body)
    client = _fake_client(
        versions={_sha1(body): {"project_id": "P", "id": "v", "version_number": "1"}},
        projects=[{"id": "P", "slug": "p", "title": "P"}],
    )

    resolved = installed.resolve_jar_files(client, [a, b])

    assert set(resolved) == {"a.jar", "b.jar"}
    assert client.get_versions_by_hashes.call_args[0][0] == [_sha1(body)]


def test_unreadable_files_are_skipped_not_fatal(tmp_path):
    good = _write_jar(tmp_path, "good.jar", b"ok")
    missing = tmp_path / "gone.jar"
    client = _fake_client(
        versions={_sha1(b"ok"): {"project_id": "P", "id": "v", "version_number": "1"}},
        projects=[{"id": "P", "slug": "p", "title": "P"}],
    )

    resolved = installed.resolve_jar_files(client, [good, missing])
    assert set(resolved) == {"good.jar"}


def test_empty_input_makes_no_requests(tmp_path):
    client = _fake_client()
    assert installed.resolve_jar_files(client, []) == {}
    client.get_versions_by_hashes.assert_not_called()


def test_api_error_propagates(tmp_path):
    """A 429 must reach the route so it can be turned into a retry_after."""
    jar = _write_jar(tmp_path, "a.jar", b"bytes")
    client = MagicMock()
    client.get_versions_by_hashes.side_effect = ModrinthApiError("nope", status_code=429)

    with pytest.raises(ModrinthApiError):
        installed.resolve_jar_files(client, [jar])


# ---------------------------------------------------------------------------
# Client bulk endpoints
# ---------------------------------------------------------------------------

def _client_with_responses(*payloads):
    """A ModrinthClient whose session returns `payloads` in order."""
    client = ModrinthClient(limiter=RateLimiter(capacity=1000, window_seconds=1.0))
    responses = []
    for payload in payloads:
        response = MagicMock()
        response.headers = {}
        response.json.return_value = payload
        response.raise_for_status.return_value = None
        responses.append(response)
    client.session = MagicMock()
    client.session.request.side_effect = responses
    return client


def test_get_versions_by_hashes_posts_the_batch():
    client = _client_with_responses({"abc": {"project_id": "P"}})
    result = client.get_versions_by_hashes(["ABC"])

    assert result == {"abc": {"project_id": "P"}}
    kwargs = client.session.request.call_args.kwargs
    # Hashes are normalised to lower case — Modrinth keys its response that way.
    assert kwargs["json"] == {"hashes": ["abc"], "algorithm": "sha1"}


def test_get_versions_by_hashes_deduplicates():
    client = _client_with_responses({})
    client.get_versions_by_hashes(["aa", "AA", "bb"])
    assert client.session.request.call_args.kwargs["json"]["hashes"] == ["aa", "bb"]


def test_get_versions_by_hashes_chunks_large_batches():
    hashes = [f"{i:040x}" for i in range(450)]
    client = _client_with_responses({}, {}, {})
    client.get_versions_by_hashes(hashes)

    # 450 hashes at BULK_CHUNK_SIZE=200 => 3 requests, not 450.
    assert client.session.request.call_count == 3
    sizes = [c.kwargs["json"]["hashes"] for c in client.session.request.call_args_list]
    assert [len(s) for s in sizes] == [200, 200, 50]


def test_get_projects_sends_ids_as_json_array():
    client = _client_with_responses([{"id": "P1"}, {"id": "P2"}])
    projects = client.get_projects(["P1", "P2"])

    assert [p["id"] for p in projects] == ["P1", "P2"]
    assert client.session.request.call_args.kwargs["params"]["ids"] == '["P1", "P2"]'


def test_bulk_helpers_short_circuit_on_empty_input():
    client = _client_with_responses()
    assert client.get_versions_by_hashes([]) == {}
    assert client.get_projects([]) == []
    client.session.request.assert_not_called()


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------

def _make_server(tmp_servers_root, name="Srv", port=25611):
    from backend.server import storage
    return storage.create_server({
        "name": name,
        "version": "1.20.1",
        "loader": "fabric",
        "port": port,
        "installPath": "srv-mods",
        "memory": 4,
    })


def test_route_returns_resolved_map(client, tmp_servers_root, tmp_path):
    server = _make_server(tmp_servers_root)
    mods_dir = tmp_path / "mods"
    _write_jar(mods_dir, "a.jar", b"bytes")

    with patch("backend.modrinth.routes._resolve_mods_folder",
               return_value=(str(mods_dir), None)), \
         patch("backend.modrinth.routes.modrinth_client") as mc:
        mc.get_versions_by_hashes.return_value = {
            _sha1(b"bytes"): {"project_id": "P", "id": "v", "version_number": "1.0"}
        }
        mc.get_projects.return_value = [{"id": "P", "slug": "p", "title": "Proj"}]
        resp = client.get(f"/api/modrinth/servers/{server['id']}/resolve-installed")

    assert resp.status_code == 200
    assert resp.get_json()["resolved"]["a.jar"]["title"] == "Proj"


def test_route_ignores_non_jar_files(client, tmp_servers_root, tmp_path):
    server = _make_server(tmp_servers_root, name="S2", port=25612)
    mods_dir = tmp_path / "mods"
    _write_jar(mods_dir, "a.jar", b"bytes")
    _write_jar(mods_dir, "notes.txt", b"text")
    (mods_dir / "subdir").mkdir()

    with patch("backend.modrinth.routes._resolve_mods_folder",
               return_value=(str(mods_dir), None)), \
         patch("backend.modrinth.routes.modrinth_client") as mc:
        mc.get_versions_by_hashes.return_value = {}
        mc.get_projects.return_value = []
        resp = client.get(f"/api/modrinth/servers/{server['id']}/resolve-installed")

    assert resp.status_code == 200
    assert mc.get_versions_by_hashes.call_args[0][0] == [_sha1(b"bytes")]


def test_route_handles_a_missing_mods_folder(client, tmp_servers_root, tmp_path):
    server = _make_server(tmp_servers_root, name="S3", port=25613)
    with patch("backend.modrinth.routes._resolve_mods_folder",
               return_value=(str(tmp_path / "nope"), None)):
        resp = client.get(f"/api/modrinth/servers/{server['id']}/resolve-installed")

    assert resp.status_code == 200
    assert resp.get_json() == {"resolved": {}}


def test_route_unknown_server_is_404(client, tmp_servers_root):
    resp = client.get("/api/modrinth/servers/srv_nope/resolve-installed")
    assert resp.status_code == 404


def test_route_forwards_rate_limit_with_retry_after(client, tmp_servers_root, tmp_path):
    """The frontend's backoff reads `retry_after` off the body; a proxy or curl
    reads the header. Both must be present."""
    server = _make_server(tmp_servers_root, name="S4", port=25614)
    mods_dir = tmp_path / "mods"
    _write_jar(mods_dir, "a.jar", b"bytes")

    with patch("backend.modrinth.routes._resolve_mods_folder",
               return_value=(str(mods_dir), None)), \
         patch("backend.modrinth.routes.modrinth_client") as mc:
        mc.get_versions_by_hashes.side_effect = ModrinthApiError(
            "Too many requests", status_code=429, details={"retry_after": 12.0}
        )
        resp = client.get(f"/api/modrinth/servers/{server['id']}/resolve-installed")

    assert resp.status_code == 429
    assert resp.get_json()["retry_after"] == 12.0
    assert resp.headers["Retry-After"] == "12"
