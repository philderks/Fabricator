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


def _tar_bytes(build) -> io.BytesIO:
    """Build an in-memory tar via ``build(tf)`` and hand back a rewound buffer."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tf:
        build(tf)
    buf.seek(0)
    return buf


def _add_file(tf, name, data=b"x", mode=0o644):
    info = tarfile.TarInfo(name=name)
    info.size = len(data)
    info.mode = mode
    tf.addfile(info, io.BytesIO(data))


def _add_link(tf, name, linkname, kind=tarfile.SYMTYPE):
    info = tarfile.TarInfo(name=name)
    info.type = kind
    info.linkname = linkname
    tf.addfile(info)


def test_safe_extract_tar_materialises_internal_symlink(tmp_path):
    """opt-in ``allow_internal_links``: a relative symlink that stays inside the
    destination is recreated as a symlink. This is the Temurin JDK ``legal/``
    layout from issue #51 — every module's LICENSE points at
    ``../java.base/LICENSE`` — which the blanket refusal used to abort on."""
    from backend.utils.zip import safe_extract_tar

    buf = _tar_bytes(lambda tf: (
        _add_file(tf, "jdk/legal/java.base/LICENSE", b"GPLv2"),
        _add_link(tf, "jdk/legal/jdk.jshell/LICENSE", "../java.base/LICENSE"),
    ))

    dest = tmp_path / "dest"
    dest.mkdir()
    with tarfile.open(fileobj=buf, mode="r") as tf:
        safe_extract_tar(tf, dest, allow_internal_links=True)

    link = dest / "jdk" / "legal" / "jdk.jshell" / "LICENSE"
    assert link.is_symlink()
    assert link.read_bytes() == b"GPLv2"


def test_safe_extract_tar_materialises_internal_hardlink(tmp_path):
    """Hardlink members resolve against the archive root and are recreated as
    a link (or a copy where ``os.link`` is unavailable) — either way the
    content is there."""
    from backend.utils.zip import safe_extract_tar

    buf = _tar_bytes(lambda tf: (
        _add_file(tf, "jdk/legal/java.base/LICENSE", b"GPLv2"),
        _add_link(
            tf,
            "jdk/legal/java.rmi/LICENSE",
            "jdk/legal/java.base/LICENSE",
            kind=tarfile.LNKTYPE,
        ),
    ))

    dest = tmp_path / "dest"
    dest.mkdir()
    with tarfile.open(fileobj=buf, mode="r") as tf:
        safe_extract_tar(tf, dest, allow_internal_links=True)

    assert (dest / "jdk" / "legal" / "java.rmi" / "LICENSE").read_bytes() == b"GPLv2"


def test_safe_extract_tar_refuses_links_by_default(tmp_path):
    """The opt-in is opt-in: callers extracting untrusted archives (backup
    restore, world import) keep the blanket refusal."""
    from backend.utils.zip import safe_extract_tar

    buf = _tar_bytes(lambda tf: _add_link(tf, "link", "../java.base/LICENSE"))

    dest = tmp_path / "dest"
    dest.mkdir()
    with tarfile.open(fileobj=buf, mode="r") as tf:
        with pytest.raises(ValueError, match="link"):
            safe_extract_tar(tf, dest)


@pytest.mark.parametrize(
    "linkname",
    # The third is the prefix-sibling case: from ``dest/jdk/`` it lands on
    # ``dest-evil/``, which shares the destination's string prefix but is not
    # inside it.
    ["/etc/passwd", "../../outside/secret", "../../dest-evil/secret"],
)
def test_safe_extract_tar_refuses_escaping_links_even_when_allowed(
    tmp_path, linkname
):
    """``allow_internal_links`` only relaxes links whose target stays inside the
    destination: absolute targets and ``..`` walks out are still refused, and
    nothing is left behind."""
    from backend.utils.zip import safe_extract_tar

    buf = _tar_bytes(lambda tf: _add_link(tf, "jdk/evil", linkname))

    dest = tmp_path / "dest"
    dest.mkdir()
    with tarfile.open(fileobj=buf, mode="r") as tf:
        with pytest.raises(ValueError, match="outside destination"):
            safe_extract_tar(tf, dest, allow_internal_links=True)

    assert not (dest / "jdk" / "evil").is_symlink()


def test_safe_extract_tar_refuses_symlink_chain_escape(tmp_path):
    """A symlink pointing at an in-archive symlink that itself points out must
    be refused: the target is resolved (following links) *before* the
    containment check, so the chain cannot launder an escape."""
    from backend.utils.zip import safe_extract_tar

    (tmp_path / "outside").mkdir()
    (tmp_path / "outside" / "secret").write_text("s")

    buf = _tar_bytes(lambda tf: (
        _add_link(tf, "jdk/hop", "../../outside"),
        _add_link(tf, "jdk/gotcha", "hop/secret"),
    ))

    dest = tmp_path / "dest"
    dest.mkdir()
    with tarfile.open(fileobj=buf, mode="r") as tf:
        with pytest.raises(ValueError, match="outside destination"):
            safe_extract_tar(tf, dest, allow_internal_links=True)


def test_safe_extract_tar_preserves_exec_bits(tmp_path):
    """The manual write stream would leave every file 0o644 — a vendor JDK's
    ``bin/java`` and ``lib/jspawnhelper`` must come out executable. setuid is
    never carried over."""
    from backend.utils.zip import safe_extract_tar

    buf = _tar_bytes(lambda tf: (
        _add_file(tf, "jdk/bin/java", b"ELF", mode=0o755),
        _add_file(tf, "jdk/lib/modules", b"blob", mode=0o644),
        _add_file(tf, "jdk/bin/sneaky", b"ELF", mode=0o4755),
    ))

    dest = tmp_path / "dest"
    dest.mkdir()
    with tarfile.open(fileobj=buf, mode="r") as tf:
        safe_extract_tar(tf, dest)

    assert (dest / "jdk" / "bin" / "java").stat().st_mode & 0o111 == 0o111
    assert (dest / "jdk" / "lib" / "modules").stat().st_mode & 0o111 == 0
    sneaky = (dest / "jdk" / "bin" / "sneaky").stat().st_mode
    assert sneaky & 0o111 == 0o111
    assert sneaky & 0o4000 == 0
