"""Snapshot archive writing.

The write-side counterpart to :func:`backend.utils.zip.safe_extract_tar`.
Every archive produced here has to be one that extractor will accept, because
the only reason a snapshot exists at all is to be restored later.

Two decisions are load-bearing.

**Symlinks are dereferenced, never stored as link members.** Storing them
fails twice over:

* ``safe_extract_tar`` refuses link members, so a snapshot holding one builds
  cleanly, records as ``success``, and then fails at restore — the single
  moment it is needed.
* A stored symlink does not carry the data behind it. A server whose
  ``world/`` is a symlink onto a bigger disk would get a "safety snapshot"
  containing a dangling name and none of the world.

Dereferencing also matches the scheduled-backup path, which already copies
*through* symlinks (``shutil.copytree(..., symlinks=False)``), so both
snapshot flavours end up capturing the same bytes.

**An entry that cannot be read is skipped, not fatal.** A broken symlink, or a
file the running server deleted between the walk and the read, returns a
warning rather than aborting: a backup missing one rotated log is worth
enormously more than no backup at all. The caller surfaces the warnings on the
snapshot record (``status="warning"``), so nothing is lost silently.
"""
from __future__ import annotations

import tarfile
from pathlib import Path
from typing import Callable, Iterator, List, Optional, Tuple


def _walk_tree(
    root: Path,
    *,
    skip: Optional[Callable[[str], bool]] = None,
) -> Iterator[Tuple[Path, str]]:
    """Yield ``(path, arcname)`` for every entry under ``root``, depth-first.

    Symlinked directories ARE descended into (that is the whole point of
    dereferencing — their contents must land in the archive), which makes a
    symlink cycle possible, so every directory is recorded by its resolved
    identity and never visited twice. Directories matching ``skip`` are pruned
    rather than merely omitted, so excluding a storage dir does not cost a walk
    of every archive inside it.

    Unreadable directories are skipped: their entries simply do not appear.
    """
    visited: set[Path] = set()

    def _descend(directory: Path, prefix: str) -> Iterator[Tuple[Path, str]]:
        try:
            real = directory.resolve()
        except OSError:
            return
        if real in visited:
            return  # symlink cycle — already archived under its first name
        visited.add(real)

        try:
            entries = sorted(directory.iterdir(), key=lambda item: item.name)
        except OSError:
            return  # unreadable directory: nothing to contribute

        for entry in entries:
            arcname = f"{prefix}/{entry.name}" if prefix else entry.name
            if skip is not None and skip(arcname):
                continue
            yield entry, arcname
            # is_dir() follows the link, so a symlinked directory is descended
            # into. It swallows OSError and returns False, which is what makes
            # a broken symlink fall through to the caller's add-and-warn.
            try:
                is_dir = entry.is_dir()
            except OSError:
                continue
            if is_dir:
                yield from _descend(entry, arcname)

    yield from _descend(root, "")


def write_tree_tar(
    root: Path,
    destination: Path,
    *,
    skip: Optional[Callable[[str], bool]] = None,
) -> List[str]:
    """Archive everything under ``root`` into an uncompressed tar at ``destination``.

    ``skip`` receives each entry's archive-relative posix name and returns True
    to leave it (and, for a directory, its whole subtree) out.

    Returns a list of human-readable warnings for entries that could not be
    added. Raises only on a failure to write the archive itself — a per-entry
    read error is reported, not raised.
    """
    warnings: List[str] = []
    # dereference=True is what keeps link members out of the archive entirely:
    # symlinks are stored as the file they point at, and hardlink detection
    # (which would emit LNKTYPE members for the second occurrence) is disabled.
    with tarfile.open(destination, "w", dereference=True) as tf:
        for path, arcname in _walk_tree(root, skip=skip):
            try:
                tf.add(path, arcname=arcname, recursive=False)
            except (OSError, ValueError) as exc:
                # Broken symlink, a file the live server just deleted, a socket
                # with no tar representation — none is worth losing the backup.
                warnings.append(f"skipped {arcname}: {exc}")
    return warnings


def subtree_skipper(exclude_rel: Optional[str]) -> Optional[Callable[[str], bool]]:
    """Return a ``skip`` predicate excluding ``exclude_rel`` and its descendants.

    ``exclude_rel`` is an archive-relative posix path (the storage directory,
    when it happens to live inside the tree being archived — that is what stops
    a safety snapshot from recursively packing every previous backup). ``None``
    means nothing is excluded.
    """
    if not exclude_rel:
        return None

    prefix = exclude_rel + "/"

    def _skip(arcname: str) -> bool:
        return arcname == exclude_rel or arcname.startswith(prefix)

    return _skip
