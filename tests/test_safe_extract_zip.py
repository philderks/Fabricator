"""Path-traversal guards for ``backend.utils.zip`` (``is_within`` +
``safe_extract_zip`` / ``safe_extract_tar``)."""
from __future__ import annotations

import io
import tarfile
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


def test_is_within_rejects_prefix_sibling_and_accepts_children(tmp_path):
    """The shared containment predicate: a prefix-sibling shares the string
    prefix but is NOT inside base (the bug str.startswith had); genuine
    children and base itself are within."""
    from backend.utils.zip import is_within

    base = tmp_path / "mc1"
    base.mkdir()
    (tmp_path / "mc1-evil").mkdir()

    assert is_within(base, tmp_path / "mc1-evil" / "x") is False
    assert is_within(base, base / ".." / "outside") is False
    assert is_within(base, base / "sub" / "f") is True
    assert is_within(base, base) is True


def test_safe_extract_tar_rejects_prefix_sibling_escape(tmp_path):
    """safe_extract_tar shares is_within with safe_extract_zip: a member that
    resolves into a prefix-sibling of the destination is rejected and nothing
    is written outside."""
    from backend.utils.zip import safe_extract_tar

    destination = tmp_path / "dest"
    destination.mkdir()

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tf:
        data = b"x"
        info = tarfile.TarInfo(name="../dest-evil/pwn.txt")
        info.size = len(data)
        tf.addfile(info, io.BytesIO(data))
    buf.seek(0)

    with tarfile.open(fileobj=buf, mode="r") as tf:
        with pytest.raises(ValueError):
            safe_extract_tar(tf, destination)

    assert not (tmp_path / "dest-evil" / "pwn.txt").exists()
