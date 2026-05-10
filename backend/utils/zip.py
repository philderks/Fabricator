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
