"""Path-traversal guards and mtime round-trips for ``backend.utils.zip``
(``is_within`` + ``safe_extract_zip`` / ``safe_extract_tar``)."""
from __future__ import annotations

import io
import tarfile
import time
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


def test_safe_extract_tar_restores_file_and_dir_mtimes(tmp_path):
    """Round-trip: extracted files and dirs keep the archive's mtime, not the
    extraction time. The directory mtime is applied in a second pass, so a
    child written into it afterwards does not leave the dir stamped at "now"
    (which is exactly what would resurrect the playerdata "last seen" bug
    after a restore)."""
    from backend.utils.zip import safe_extract_tar

    old_dir = 1_500_000_000    # 2017-07-14
    old_child = 1_410_000_000  # 2014-09-06
    old_file = 1_400_000_000   # 2014-05-13

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tf:
        d = tarfile.TarInfo(name="world/")
        d.type = tarfile.DIRTYPE
        d.mtime = old_dir
        tf.addfile(d)

        data = b"hello"
        child = tarfile.TarInfo(name="world/playerdata.dat")
        child.size = len(data)
        child.mtime = old_child
        tf.addfile(child, io.BytesIO(data))

        top_data = b"top"
        top = tarfile.TarInfo(name="server.properties")
        top.size = len(top_data)
        top.mtime = old_file
        tf.addfile(top, io.BytesIO(top_data))
    buf.seek(0)

    dest = tmp_path / "dest"
    dest.mkdir()
    with tarfile.open(fileobj=buf, mode="r") as tf:
        safe_extract_tar(tf, dest)

    assert (dest / "server.properties").stat().st_mtime == pytest.approx(old_file, abs=2)
    assert (dest / "world" / "playerdata.dat").stat().st_mtime == pytest.approx(old_child, abs=2)
    # The dir keeps its own archived mtime even though a child was written
    # into it after the dir was created — proves the second pass ran.
    assert (dest / "world").stat().st_mtime == pytest.approx(old_dir, abs=2)


def test_safe_extract_zip_restores_file_and_dir_mtimes(tmp_path):
    """Round-trip for the zip helper: ``date_time`` is restored onto files and
    (second pass) directories. Symmetric with the tar round-trip above."""
    from backend.utils.zip import safe_extract_zip

    file_dt = (2020, 6, 1, 12, 0, 4)    # even seconds — DOS time is 2s-granular
    dir_dt = (2019, 3, 2, 8, 0, 0)
    child_dt = (2021, 2, 3, 9, 30, 10)

    archive = tmp_path / "a.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr(zipfile.ZipInfo("top.txt", date_time=file_dt), b"top")
        zf.writestr(zipfile.ZipInfo("world/", date_time=dir_dt), b"")
        zf.writestr(zipfile.ZipInfo("world/child.txt", date_time=child_dt), b"c")

    dest = tmp_path / "dest"
    dest.mkdir()
    with zipfile.ZipFile(archive, "r") as zf:
        safe_extract_zip(zf, dest)

    expect_file = time.mktime((*file_dt, 0, 0, -1))
    expect_dir = time.mktime((*dir_dt, 0, 0, -1))
    expect_child = time.mktime((*child_dt, 0, 0, -1))

    assert (dest / "top.txt").stat().st_mtime == pytest.approx(expect_file, abs=2)
    assert (dest / "world" / "child.txt").stat().st_mtime == pytest.approx(expect_child, abs=2)
    assert (dest / "world").stat().st_mtime == pytest.approx(expect_dir, abs=2)
