"""Safe archive extraction helpers (zip + tar).

The ``safe_extract_tar`` helper here lives next to ``safe_extract_zip``
rather than in a separate ``backend/utils/tar.py`` so the path-traversal
guard logic stays symmetric and reviewable in one place. Both helpers
use the same ``relative_to``-based check rather than a string
``startswith`` (a destination ``/x`` and a member resolving to
``/xy/...`` would slip through ``startswith``).
"""

from __future__ import annotations

import os
import shutil
import tarfile
import time
import zipfile
from pathlib import Path


def is_within(base: Path, candidate: Path) -> bool:
    """Return True iff ``candidate`` is ``base`` itself or a path beneath it.

    The single source of truth for path containment. Uses
    :py:meth:`Path.relative_to` rather than a ``str.startswith`` prefix compare
    — the latter accepts sibling-prefix escapes (``base=/x/mc1`` and
    ``candidate=/x/mc1-evil/...`` share the ``/x/mc1`` prefix but the second is
    NOT inside the first). Both paths are resolved first so ``..`` segments and
    symlinks are collapsed before the comparison.
    """
    base_resolved = Path(base).resolve()
    candidate_resolved = Path(candidate).resolve()
    try:
        candidate_resolved.relative_to(base_resolved)
        return True
    except ValueError:
        return False


def _zip_member_mtime(member: zipfile.ZipInfo) -> float | None:
    """Convert a ``ZipInfo.date_time`` 6-tuple to epoch seconds.

    Zip stores the modification time as ``(year, month, day, hour, minute,
    second)`` in the archive's local time with no timezone. :func:`time.mktime`
    interprets the tuple in the host's local zone (``isdst=-1`` lets libc pick
    the DST offset). Returns ``None`` when the stored date is unusable (some
    tools emit a zero/out-of-range date) so extraction never aborts on it.
    """
    try:
        return time.mktime((*member.date_time, 0, 0, -1))
    except (ValueError, OverflowError):
        return None


def safe_extract_zip(zf: zipfile.ZipFile, destination: Path) -> None:
    """Extract every member of ``zf`` into ``destination`` rejecting traversal.

    Resolves each member's target path and verifies it stays under
    ``destination`` via :py:meth:`Path.relative_to`. The ``relative_to``
    check (rather than a ``startswith`` string compare) correctly rejects
    sibling-prefix escapes like a destination ``/x`` and a member resolving
    to ``/xy/...``. Raises :class:`ValueError` for any traversal attempt
    (``..`` segments, absolute paths, etc).

    Files are streamed via :func:`shutil.copyfileobj` to avoid loading
    entire members into memory.

    Member modification times are restored from ``ZipInfo.date_time`` (see
    :func:`safe_extract_tar` for the rationale — the two helpers are kept
    symmetric on purpose). Directory mtimes are applied in a second pass
    *after* every file is written, otherwise writing a child bumps its
    parent directory's mtime back to "now".
    """
    destination = Path(destination).resolve()
    dir_mtimes: list[tuple[Path, float]] = []
    for member in zf.infolist():
        # Symlink members carry the target path as the body, materialised
        # via the high byte of ``external_attr`` (Unix file mode). Refuse
        # them at the boundary — once written as a regular file with the
        # target path as content they are inert, but legacy tooling that
        # later sees a symlink-typed entry could re-create it and bypass
        # the relative_to check below. Easier to reject up-front.
        unix_mode = (member.external_attr >> 16) & 0o170000
        if unix_mode == 0o120000:
            raise ValueError(
                f"Archive member is a symlink (refusing): {member.filename!r}"
            )

        target = (destination / member.filename).resolve()
        if not is_within(destination, target):
            raise ValueError(
                f"Archive member escapes destination: {member.filename!r}"
            )

        mtime = _zip_member_mtime(member)

        if member.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            if mtime is not None:
                dir_mtimes.append((target, mtime))
            continue

        target.parent.mkdir(parents=True, exist_ok=True)
        with zf.open(member, "r") as source, open(target, "wb") as sink:
            shutil.copyfileobj(source, sink)
        if mtime is not None:
            os.utime(target, (mtime, mtime))

    _restore_dir_mtimes(dir_mtimes)


def _restore_dir_mtimes(dir_mtimes: list[tuple[Path, float]]) -> None:
    """Apply saved directory mtimes as a second pass.

    Called only after every regular file has been written: setting a
    directory's mtime is pointless while children are still being created
    inside it (each create bumps the parent back to "now"). ``os.utime`` on
    one directory does not touch any other, so the order here is irrelevant.
    Best-effort — a missing/locked directory must not abort the extraction.
    """
    for target, mtime in dir_mtimes:
        try:
            os.utime(target, (mtime, mtime))
        except OSError:
            pass


def safe_extract_tar(tf: tarfile.TarFile, destination: Path) -> None:
    """Extract every member of ``tf`` into ``destination`` rejecting traversal.

    Symmetric with :func:`safe_extract_zip`:

    - Resolves each member's target path and verifies it stays under
      ``destination`` via :py:meth:`Path.relative_to` (rejects sibling
      escapes like dest=``/x`` member=``/xy/...``).
    - Refuses symlink and hardlink members up-front — Python's tar
      extractor is happy to materialise a symlink that points outside the
      destination, and a later read through that symlink would silently
      cross the boundary.
    - Skips device / fifo members (we don't need them for Minecraft
      server data and they're a footgun on POSIX hosts).

    Raises :class:`ValueError` for any traversal attempt or refused
    member type. Regular files are streamed via :func:`shutil.copyfileobj`
    to avoid loading entire members into memory.

    Member modification times are restored from ``TarInfo.mtime`` — the
    manual stream (``open(target, "wb")``) would otherwise stamp every file
    with the extraction time, which breaks any consumer that reads a file's
    mtime as a real event time (e.g. playerdata "last seen"). Directory
    mtimes are applied in a second pass *after* every file is written,
    otherwise writing a child bumps its parent directory's mtime back to
    "now".
    """
    destination = Path(destination).resolve()
    dir_mtimes: list[tuple[Path, float]] = []
    for member in tf.getmembers():
        if member.issym() or member.islnk():
            raise ValueError(
                f"Archive member is a link (refusing): {member.name!r}"
            )
        if member.isdev() or member.isfifo():
            # Silently skip — not relevant to MC server backups, refusing
            # outright would just confuse callers extracting a third-party
            # tar that happens to include unrelated control members.
            continue

        target = (destination / member.name).resolve()
        if not is_within(destination, target):
            raise ValueError(
                f"Archive member escapes destination: {member.name!r}"
            )

        if member.isdir():
            target.mkdir(parents=True, exist_ok=True)
            dir_mtimes.append((target, member.mtime))
            continue

        target.parent.mkdir(parents=True, exist_ok=True)
        source = tf.extractfile(member)
        if source is None:
            # Some special member types (e.g. GNU sparse headers without
            # data) yield None — just skip them rather than crash.
            continue
        try:
            with open(target, "wb") as sink:
                shutil.copyfileobj(source, sink)
        finally:
            source.close()
        os.utime(target, (member.mtime, member.mtime))

    _restore_dir_mtimes(dir_mtimes)
