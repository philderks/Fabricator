"""Safe zipfile extraction helpers."""

from __future__ import annotations

import shutil
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
