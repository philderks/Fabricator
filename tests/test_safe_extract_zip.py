"""Path-traversal guards for ``backend.utils.zip.safe_extract_zip``."""
from __future__ import annotations

import zipfile

import pytest


def test_safe_extract_zip_rejects_prefix_sibling_escape(tmp_path):
    """Destination is `x/`; a member that resolves to `xy/...` must be rejected.

    The legacy startswith check would wrongly allow this because the string
    "xy/..." starts with "x".
    """
    from backend.utils.zip import safe_extract_zip

    destination = tmp_path / "x"
    destination.mkdir()
    sibling = tmp_path / "xy"

    archive = tmp_path / "evil.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("../xy/evil.jar", b"pwn")

    with zipfile.ZipFile(archive, "r") as zf:
        with pytest.raises((ValueError, RuntimeError)):
            safe_extract_zip(zf, destination)

    assert not (sibling / "evil.jar").exists()


def test_safe_extract_zip_rejects_absolute_path(tmp_path):
    """Members with absolute paths must not escape the destination."""
    from backend.utils.zip import safe_extract_zip

    destination = tmp_path / "x"
    destination.mkdir()

    archive = tmp_path / "evil.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("/tmp/escape.jar", b"pwn")

    with zipfile.ZipFile(archive, "r") as zf:
        with pytest.raises((ValueError, RuntimeError)):
            safe_extract_zip(zf, destination)
