"""Safe archive extraction helpers (zip + tar).

The ``safe_extract_tar`` helper here lives next to ``safe_extract_zip``
rather than in a separate ``backend/utils/tar.py`` so the path-traversal
guard logic stays symmetric and reviewable in one place. Both helpers
use the same ``relative_to``-based check rather than a string
``startswith`` (a destination ``/x`` and a member resolving to
``/xy/...`` would slip through ``startswith``).
"""

from __future__ import annotations

import shutil
import tarfile
import zipfile
from pathlib import Path


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
    """
    destination = Path(destination).resolve()
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
        try:
            target.relative_to(destination)
        except ValueError as exc:
            raise ValueError(
                f"Archive member escapes destination: {member.filename!r}"
            ) from exc

        if member.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue

        target.parent.mkdir(parents=True, exist_ok=True)
        with zf.open(member, "r") as source, open(target, "wb") as sink:
            shutil.copyfileobj(source, sink)


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
    """
    destination = Path(destination).resolve()
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
        try:
            target.relative_to(destination)
        except ValueError as exc:
            raise ValueError(
                f"Archive member escapes destination: {member.name!r}"
            ) from exc

        if member.isdir():
            target.mkdir(parents=True, exist_ok=True)
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
