"""C3 (+H10): download_mod must sanitize filename and verify hash."""
from __future__ import annotations

import hashlib
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
