"""Snapshot archives must survive symlinks and a live server mutating the tree.

Two defects are pinned here, both of the "backup looks fine until you need it"
kind:

* Safety snapshots tarred the live dir with symlinks preserved as link members.
  ``safe_extract_tar`` refuses link members, so the snapshot recorded as
  ``success`` and then failed at restore — and a symlinked ``world/`` meant the
  archive never held the world data in the first place.
* The staging copy for a scheduled backup runs against a RUNNING server. One
  file rotated away mid-copy, or one broken symlink anywhere in the tree,
  failed the entire backup.
"""
from __future__ import annotations

import os
import shutil
import tarfile
from pathlib import Path

import pytest

from backend.backups import archive
from backend.utils.zip import safe_extract_tar


# --------------------------------------------------------------------------- #
# write_tree_tar — the shared safety-snapshot writer
# --------------------------------------------------------------------------- #

def _build(tree: Path) -> Path:
    out = tree.parent / "out.tar"
    archive.write_tree_tar(tree, out)
    return out


def test_symlinked_file_is_stored_as_its_content(tmp_path):
    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "real.txt").write_text("PAYLOAD", encoding="utf-8")
    os.symlink(tree / "real.txt", tree / "link.txt")

    out = _build(tree)

    with tarfile.open(out) as tf:
        assert not any(m.issym() or m.islnk() for m in tf.getmembers())
        assert tf.extractfile("link.txt").read() == b"PAYLOAD"


def test_symlinked_directory_contents_are_captured(tmp_path):
    """A server whose world/ is a symlink onto another disk must still get its
    world into the snapshot — the old writer stored a dangling name and no data."""
    tree = tmp_path / "tree"
    tree.mkdir()
    elsewhere = tmp_path / "elsewhere"
    (elsewhere / "region").mkdir(parents=True)
    (elsewhere / "region" / "r.0.0.mca").write_text("CHUNKS", encoding="utf-8")
    os.symlink(elsewhere, tree / "world")

    out = _build(tree)

    with tarfile.open(out) as tf:
        names = set(tf.getnames())
        assert not any(m.issym() or m.islnk() for m in tf.getmembers())
        assert "world/region/r.0.0.mca" in names
        assert tf.extractfile("world/region/r.0.0.mca").read() == b"CHUNKS"


def test_archive_with_symlinks_is_restorable(tmp_path):
    """The whole point: what the writer produces, the strict extractor accepts."""
    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "real.txt").write_text("PAYLOAD", encoding="utf-8")
    os.symlink(tree / "real.txt", tree / "link.txt")

    out = _build(tree)
    destination = tmp_path / "restored"
    destination.mkdir()

    with tarfile.open(out) as tf:
        safe_extract_tar(tf, destination)  # strict: must not raise

    assert (destination / "link.txt").read_text() == "PAYLOAD"


def test_broken_symlink_is_skipped_with_a_warning(tmp_path):
    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "keep.txt").write_text("KEEP", encoding="utf-8")
    os.symlink(tmp_path / "does-not-exist", tree / "dangling")

    out = tree.parent / "out.tar"
    warnings = archive.write_tree_tar(tree, out)

    assert len(warnings) == 1
    assert "dangling" in warnings[0]
    with tarfile.open(out) as tf:
        assert "keep.txt" in tf.getnames()      # the rest of the backup survived


def test_symlink_cycle_terminates(tmp_path):
    """Following symlinked directories makes a cycle possible; it must not hang
    or recurse forever."""
    tree = tmp_path / "tree"
    (tree / "sub").mkdir(parents=True)
    (tree / "sub" / "f.txt").write_text("F", encoding="utf-8")
    os.symlink(tree, tree / "sub" / "loop")

    out = tree.parent / "out.tar"
    archive.write_tree_tar(tree, out)

    with tarfile.open(out) as tf:
        assert "sub/f.txt" in tf.getnames()


def test_subtree_skipper_prunes_the_storage_dir(tmp_path):
    tree = tmp_path / "tree"
    (tree / "data" / "backups").mkdir(parents=True)
    (tree / "data" / "backups" / "old.tar").write_text("OLD", encoding="utf-8")
    (tree / "data" / "keep.dat").write_text("KEEP", encoding="utf-8")

    out = tree.parent / "out.tar"
    archive.write_tree_tar(
        tree, out, skip=archive.subtree_skipper("data/backups")
    )

    with tarfile.open(out) as tf:
        names = set(tf.getnames())
    assert "data/keep.dat" in names
    assert not any(n.startswith("data/backups") for n in names), names


def test_subtree_skipper_is_none_without_an_exclusion(tmp_path):
    assert archive.subtree_skipper(None) is None
    assert archive.subtree_skipper("") is None


# --------------------------------------------------------------------------- #
# Live-server churn during the staging copy
# --------------------------------------------------------------------------- #

def _service():
    from backend.backups import service
    return service


def test_broken_symlink_does_not_fail_the_staging_copy(tmp_path):
    """With symlinks=False copytree resolves links, so a dangling one used to
    fail every run deterministically."""
    service = _service()
    src = tmp_path / "src"
    src.mkdir()
    (src / "server.properties").write_text("port=25565\n", encoding="utf-8")
    os.symlink(tmp_path / "gone", src / "dangling")

    warnings = service._copy_tree_with_exclusions(src, tmp_path / "dst", [])

    assert warnings == []
    assert (tmp_path / "dst" / "server.properties").exists()


def test_vanished_file_is_downgraded_to_a_warning(tmp_path):
    """A file the running server deleted mid-copy must not fail the backup."""
    service = _service()
    src = tmp_path / "src"
    src.mkdir()
    missing = src / "logs" / "rotated.log"

    error = shutil.Error([(str(missing), "/dst/rotated.log", "No such file")])
    warnings = service._classify_copy_errors(error, src)

    assert len(warnings) == 1
    assert "removed during backup" in warnings[0]
    assert "rotated.log" in warnings[0]


def test_a_real_copy_error_still_fails_the_backup(tmp_path):
    """An entry still on disk is a genuine problem (permissions, full disk) and
    must not be masked by the vanished-file tolerance."""
    service = _service()
    src = tmp_path / "src"
    src.mkdir()
    present = src / "present.txt"
    present.write_text("STILL HERE", encoding="utf-8")

    error = shutil.Error([(str(present), "/dst/present.txt", "Permission denied")])
    with pytest.raises(shutil.Error):
        service._classify_copy_errors(error, src)


def test_mixed_errors_fail_rather_than_partially_warn(tmp_path):
    service = _service()
    src = tmp_path / "src"
    src.mkdir()
    present = src / "present.txt"
    present.write_text("STILL HERE", encoding="utf-8")

    error = shutil.Error([
        (str(src / "gone.txt"), "/dst/gone.txt", "No such file"),
        (str(present), "/dst/present.txt", "Permission denied"),
    ])
    with pytest.raises(shutil.Error):
        service._classify_copy_errors(error, src)
