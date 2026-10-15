"""C3 (+H10): download_mod must sanitize filename and verify hash."""
from __future__ import annotations

import hashlib
import os
import stat
from pathlib import Path

import pytest


class _FakeResponse:
    def __init__(self, body: bytes, status_code: int = 200):
        self._body = body
        self.status_code = status_code
        self.headers = {}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def iter_content(self, chunk_size=8192):
        view = memoryview(self._body)
        for i in range(0, len(view), chunk_size):
            yield bytes(view[i : i + chunk_size])

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def _make_client(monkeypatch, body: bytes):
    from backend.modrinth.client import ModrinthClient

    client = ModrinthClient()
    monkeypatch.setattr(
        client.session,
        "request",
        lambda method, url, **kw: _FakeResponse(body),
    )
    return client


def test_download_mod_rejects_parent_traversal_in_url(monkeypatch, tmp_path):
    client = _make_client(monkeypatch, b"mod-bytes")
    bad_url = "https://cdn.modrinth.com/..%2F..%2Fevil.jar"
    with pytest.raises(Exception) as excinfo:
        client.download_mod(bad_url, tmp_path)
    assert "invalid" in str(excinfo.value).lower() or "path" in str(excinfo.value).lower() or "unsafe" in str(excinfo.value).lower()


def test_download_mod_rejects_slash_in_filename(monkeypatch, tmp_path):
    client = _make_client(monkeypatch, b"mod-bytes")
    bad_url = "https://cdn.modrinth.com/foo/bar/../evil.jar"
    with pytest.raises(Exception):
        client.download_mod(bad_url, tmp_path)
    assert not (tmp_path.parent / "evil.jar").exists()


def test_download_mod_verifies_sha512(monkeypatch, tmp_path):
    body = b"clean-mod-bytes"
    bad_hash = "0" * 128
    good_hash = hashlib.sha512(body).hexdigest()

    client = _make_client(monkeypatch, body)

    with pytest.raises(Exception):
        client.download_mod(
            "https://cdn.modrinth.com/sodium.jar",
            tmp_path,
            hashes={"sha512": bad_hash},
        )
    assert not (tmp_path / "sodium.jar").exists()

    saved = client.download_mod(
        "https://cdn.modrinth.com/sodium.jar",
        tmp_path,
        hashes={"sha512": good_hash},
    )
    assert saved is not None
    assert saved.exists()
    assert saved.read_bytes() == body


def test_download_mod_accepts_plain_jar_filename(monkeypatch, tmp_path):
    client = _make_client(monkeypatch, b"jarbytes")
    saved = client.download_mod(
        "https://cdn.modrinth.com/data/ABC/versions/XYZ/sodium-0.5.jar",
        tmp_path,
    )
    assert saved == tmp_path / "sodium-0.5.jar"
    assert saved.read_bytes() == b"jarbytes"


def _assert_no_staging_files(folder: Path) -> None:
    assert list(folder.glob(".fabricator-download-*.part")) == []


@pytest.mark.parametrize("algorithm", ["sha1", "sha512"])
def test_failed_same_name_download_preserves_existing_jar(monkeypatch, tmp_path, algorithm):
    """A bad download must never remove the previously installed mod."""
    previous = tmp_path / "sodium.jar"
    previous.write_bytes(b"old working mod")

    client = _make_client(monkeypatch, b"new corrupted mod")
    expected_hash = getattr(hashlib, algorithm)(b"expected new mod").hexdigest()
    from backend.modrinth.client import ModrinthApiError

    with pytest.raises(ModrinthApiError, match="mismatch"):
        client.download_mod(
            "https://cdn.modrinth.com/sodium.jar",
            tmp_path,
            hashes={algorithm: expected_hash},
        )

    assert previous.read_bytes() == b"old working mod"
    _assert_no_staging_files(tmp_path)


def test_stream_failure_preserves_existing_jar(monkeypatch, tmp_path):
    """Even after receiving some bytes, a network error must not overwrite a jar."""
    import requests
    from backend.modrinth.client import ModrinthApiError, ModrinthClient

    previous = tmp_path / "sodium.jar"
    previous.write_bytes(b"old working mod")

    class InterruptedResponse(_FakeResponse):
        def iter_content(self, chunk_size=8192):
            yield b"incomplete new jar"
            raise requests.exceptions.ChunkedEncodingError("connection closed")

    client = ModrinthClient()
    monkeypatch.setattr(
        client.session, "request", lambda *args, **kwargs: InterruptedResponse(b"")
    )

    with pytest.raises(ModrinthApiError, match="Failed to save mod file"):
        client.download_mod("https://cdn.modrinth.com/sodium.jar", tmp_path)

    assert previous.read_bytes() == b"old working mod"
    _assert_no_staging_files(tmp_path)


def test_same_name_success_replaces_existing_jar_atomically(monkeypatch, tmp_path):
    old_jar = tmp_path / "sodium.jar"
    old_jar.write_bytes(b"old jar")
    new_contents = b"valid updated jar"
    client = _make_client(monkeypatch, new_contents)

    result = client.download_mod(
        "https://cdn.modrinth.com/sodium.jar",
        tmp_path,
        hashes={"sha512": hashlib.sha512(new_contents).hexdigest()},
    )

    assert result == old_jar
    assert old_jar.read_bytes() == new_contents
    _assert_no_staging_files(tmp_path)


def test_replace_failure_preserves_old_jar_and_removes_temp(monkeypatch, tmp_path):
    from backend.modrinth.client import ModrinthApiError, ModrinthClient

    old_jar = tmp_path / "sodium.jar"
    old_jar.write_bytes(b"keep old jar")
    client = _make_client(monkeypatch, b"new mod")

    def fail_replace(source, target):
        raise PermissionError("target jar is locked")

    monkeypatch.setattr("backend.modrinth.client.os.replace", fail_replace)

    with pytest.raises(ModrinthApiError, match="target jar is locked"):
        client.download_mod("https://cdn.modrinth.com/sodium.jar", tmp_path)

    assert old_jar.read_bytes() == b"keep old jar"
    _assert_no_staging_files(tmp_path)


def test_failed_new_download_leaves_no_partial_file(monkeypatch, tmp_path):
    from backend.modrinth.client import ModrinthApiError

    client = _make_client(monkeypatch, b"invalid jar")
    with pytest.raises(ModrinthApiError, match="SHA-1 mismatch"):
        client.download_mod(
            "https://cdn.modrinth.com/sodium.jar",
            tmp_path,
            hashes={"sha1": hashlib.sha1(b"valid jar").hexdigest()},
        )

    assert not (tmp_path / "sodium.jar").exists()
    _assert_no_staging_files(tmp_path)


def test_install_route_failed_download_preserves_same_name_jar(
    client, app, tmp_servers_root, monkeypatch
):
    """A failed install response must leave the existing same-name jar installed."""
    from backend.modrinth import routes as modrinth_routes
    from backend.server import storage

    with app.app_context():
        server = storage.create_server({
            "name": "Download test",
            "version": "1.21.4",
            "loader": "fabric",
            "port": 25991,
            "installPath": "download-test",
        })

    folder = tmp_servers_root / "servers" / "download-test" / "mods"
    folder.mkdir(parents=True)
    existing = folder / "sodium.jar"
    existing.write_bytes(b"working version")

    monkeypatch.setattr(
        modrinth_routes.modrinth_client,
        "get_project_download_url",
        lambda **kwargs: {
            "url": "https://cdn.modrinth.com/sodium.jar",
            "hashes": {"sha512": hashlib.sha512(b"valid download").hexdigest()},
            "version_id": "v2",
            "version_number": "2.0",
        },
    )
    monkeypatch.setattr(
        modrinth_routes.modrinth_client.session,
        "request",
        lambda *args, **kwargs: _FakeResponse(b"corrupted download"),
    )

    response = client.post(
        "/api/modrinth/mod/sodium/install",
        json={
            "server_id": server["id"],
            "mc_version": "1.21.4",
            "loader": "fabric",
            "replaces": "sodium.jar",
        },
    )

    assert response.status_code >= 400
    assert "mismatch" in response.get_json()["error"]
    assert existing.read_bytes() == b"working version"
    _assert_no_staging_files(folder)


@pytest.mark.skipif(os.name != "posix", reason="POSIX file mode permissions only")
def test_downloaded_jar_uses_default_file_permissions(monkeypatch, tmp_path):
    """The staged file should follow umask, not NamedTemporaryFile's fixed 0600."""
    client = _make_client(monkeypatch, b"valid jar")
    previous_umask = os.umask(0o022)
    try:
        result = client.download_mod(
            "https://cdn.modrinth.com/sodium.jar",
            tmp_path,
        )
        assert stat.S_IMODE(result.stat().st_mode) == 0o644
    finally:
        os.umask(previous_umask)
