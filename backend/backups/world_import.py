"""World import orchestrator.

Imports an uploaded world archive (zip / tar / tar.gz) onto a server,
**replacing** its active world. Modelled on :mod:`backend.backups.restore`
but scoped to the world directories only (``<levelName>`` and its
``_nether`` / ``_the_end`` siblings) rather than the whole server tree.

Sequence (``run_world_import``):

1. Acquire the per-server lock and stop the server (unconditionally —
   the world dirs hold open file handles while the JVM runs).
2. **Mandatory safety snapshot** of the live server dir into
   ``<install>/backups`` (``type="safety"``). Any exception here aborts
   the import BEFORE the live tree is touched and restarts the server.
3. Extract the upload into a staging dir via the traversal-safe
   ``safe_extract_*`` helpers.
4. **Normalize layout.** Two source shapes are accepted:

   - *Server* worlds — ``world/`` + ``world_nether/`` + ``world_the_end/``
     siblings (or a bare single-dimension world). Copied straight across,
     renamed to the target ``levelName``.
   - *Singleplayer* saves — one folder whose Nether/End live inside it as
     ``DIM-1/`` / ``DIM1/``. Converted to the server split:
     ``<L>/`` (minus the DIM dirs), ``<L>_nether/DIM-1/``,
     ``<L>_the_end/DIM1/``.

5. Swap the normalized dirs onto the live install (move existing world
   dirs aside, move new ones in, rmtree the old on success / roll back on
   failure).
6. Restart the server if it was running before step 1.

The on-disk uploaded archive is consumed (deleted) once extraction
succeeds. Progress is reported through :mod:`backend.backups.progress`
like backups and restores; the frontend polls ``GET /api/backup-jobs/<id>``.
"""
from __future__ import annotations

import logging
import os
import shutil
import tarfile
import threading
import time
import uuid
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from backend.backups import progress, storage
from backend.server import storage as server_storage
from backend.server.locks import get_server_lock
from backend.server.registry import get_server_process_registry
from backend.utils.zip import safe_extract_tar, safe_extract_zip


logger = logging.getLogger(__name__)

# Upload size cap. Worlds are large; default 10 GiB but operators on small
# hosts (or behind a proxy with its own body cap) can lower it. Enforced
# while streaming the request body so an oversized upload never lands fully
# on disk.
_DEFAULT_MAX_UPLOAD_BYTES = 10 * 1024 * 1024 * 1024


def max_upload_bytes() -> int:
    """Return the configured upload cap in bytes (env override, clamped >0)."""
    raw = os.environ.get("FABRICATOR_MAX_WORLD_UPLOAD_BYTES")
    if raw:
        try:
            value = int(raw)
            if value > 0:
                return value
        except (TypeError, ValueError):
            logger.warning(
                "Ignoring invalid FABRICATOR_MAX_WORLD_UPLOAD_BYTES=%r", raw
            )
    return _DEFAULT_MAX_UPLOAD_BYTES


class UploadTooLargeError(Exception):
    """Raised when the streamed upload exceeds :func:`max_upload_bytes`."""


class InvalidWorldArchiveError(Exception):
    """Raised when an upload is not a readable world archive."""


# Names that mark a directory as a Minecraft world / a singleplayer save.
_LEVEL_DAT = "level.dat"
_SP_DIM_DIRS = ("DIM-1", "DIM1")  # nether, end inside a singleplayer save


# ---------------------------------------------------------------------------
# Upload streaming + cheap validation (called synchronously by the route)
# ---------------------------------------------------------------------------


def stream_upload_to_temp(stream, dest: Path, *, max_bytes: int) -> int:
    """Stream ``stream`` to ``dest`` in chunks, capping at ``max_bytes``.

    Returns the number of bytes written. Raises :class:`UploadTooLargeError`
    (and unlinks the partial file) once the cap is exceeded, so a hostile or
    fat-fingered upload can't fill the disk.
    """
    written = 0
    chunk_size = 1024 * 1024
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(dest, "wb") as sink:
            while True:
                chunk = stream.read(chunk_size)
                if not chunk:
                    break
                written += len(chunk)
                if written > max_bytes:
                    raise UploadTooLargeError(
                        f"Upload exceeds the {max_bytes}-byte limit"
                    )
                sink.write(chunk)
    except BaseException:
        dest.unlink(missing_ok=True)
        raise
    return written


def validate_upload_archive(path: Path) -> str:
    """Confirm ``path`` is a readable zip/tar containing a ``level.dat``.

    Returns the detected archive kind (``"zip"`` or ``"tar"``). Raises
    :class:`InvalidWorldArchiveError` if the file can't be opened as either,
    or if no ``level.dat`` member is present (i.e. it isn't a world). Reads
    only the archive's member listing — no extraction — so it's cheap enough
    to run inline before spawning the worker.
    """
    kind, names = _list_archive_names(path)
    # _find_level_dat_root returns None only when NO level.dat exists; a world
    # sitting at the archive root yields "" (empty string). `not ""` is True, so
    # a truthiness check would wrongly reject the common "zip the world folder's
    # contents" layout. Distinguish absent (None) from root-level ("").
    if _find_level_dat_root(names) is None:
        raise InvalidWorldArchiveError(
            "Archive does not contain a level.dat — it is not a Minecraft world"
        )
    return kind


# ---------------------------------------------------------------------------
# Async entry point
# ---------------------------------------------------------------------------


def run_world_import_async(
    server_id: str, archive_path: Path, *, original_name: str
) -> str:
    """Spawn a daemon thread to import ``archive_path`` onto ``server_id``."""
    job_id = progress.generate_job_id("bjw")
    progress.update(
        job_id,
        phase="starting",
        job_id=job_id,
        kind="world_import",
        server_id=server_id,
        file_name=original_name,
    )

    def _runner() -> None:
        try:
            run_world_import(
                server_id,
                archive_path,
                original_name=original_name,
                job_id=job_id,
            )
        except Exception as exc:  # pragma: no cover - belt and braces
            logger.exception("Unhandled error in world-import worker")
            progress.update(job_id, phase="failed", error=str(exc))

    threading.Thread(
        target=_runner,
        name=f"world-import-{server_id}",
        daemon=True,
    ).start()
    return job_id


def run_world_import(
    server_id: str,
    archive_path: Path,
    *,
    original_name: str,
    job_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Run the full world-import sequence synchronously.

    Returns the ``type="import"`` snapshot record on success. On failure,
    records a best-effort error snapshot, restarts the server if it was
    running, and re-raises. The uploaded ``archive_path`` is always removed
    before returning.
    """
    if job_id is None:
        job_id = progress.generate_job_id("bjw")
        progress.update(
            job_id,
            phase="starting",
            job_id=job_id,
            kind="world_import",
            server_id=server_id,
            file_name=original_name,
        )

    archive_path = Path(archive_path)
    server = server_storage.get_server(server_id)
    if not server:
        progress.update(job_id, phase="failed", error="Server not found")
        archive_path.unlink(missing_ok=True)
        raise ValueError(f"Server {server_id!r} not found")

    registry = get_server_process_registry()
    install_path = registry.resolve_install_path(server)
    level_name = (server.get("levelName") or "world").strip() or "world"
    safety_storage = install_path / "backups"
    safety_storage.mkdir(parents=True, exist_ok=True)

    server_lock = get_server_lock(server_id)
    server_lock.acquire()
    start_time = time.monotonic()
    was_running = False
    staging_root: Optional[Path] = None
    try:
        runtime = registry.get_status(server_id) or {}
        was_running = runtime.get("status") == "running"
        if was_running:
            progress.update(job_id, phase="stopping_server")
            stop_result = registry.stop_server(server_id)
            if stop_result.get("status") != "stopped":
                raise RuntimeError(
                    "Failed to stop server before world import: "
                    f"{stop_result.get('message', 'unknown error')}"
                )
            server_storage.update_server_status(server_id, "stopped")

        # MANDATORY safety snapshot — any failure aborts before we touch
        # the live world dirs.
        progress.update(job_id, phase="safety_snapshot")
        try:
            safety = _write_safety_snapshot(
                install_path=install_path,
                storage_path=safety_storage,
                server_id=server_id,
            )
        except Exception as exc:
            logger.exception("Safety snapshot failed — aborting world import")
            progress.update(
                job_id, phase="failed", error=f"Safety snapshot failed: {exc}"
            )
            _record_error(
                server_id,
                start_time,
                message=f"Safety snapshot failed: {exc}",
            )
            raise

        # Extract the upload into staging.
        progress.update(job_id, phase="extracting")
        staging_root = install_path.parent / (
            f".worldimport-{server_id}-"
            f"{time.strftime('%Y%m%d%H%M%S', time.gmtime())}-{uuid.uuid4().hex[:6]}"
        )
        extract_root = staging_root / "extract"
        extract_root.mkdir(parents=True, exist_ok=False)
        _extract_upload(archive_path, extract_root)

        # Detect layout and normalise into target world dirs.
        progress.update(job_id, phase="converting")
        normalized_root = staging_root / "normalized"
        normalized_root.mkdir(parents=True, exist_ok=False)
        detection = detect_world_layout(extract_root)
        produced = normalize_world(
            world_root=detection["world_root"],
            layout=detection["layout"],
            level_name=level_name,
            destination=normalized_root,
        )

        # Swap the produced world dirs onto the live install.
        progress.update(job_id, phase="swapping")
        _swap_world_dirs(install_path, normalized_root, produced, server_id)

        duration = round(time.monotonic() - start_time, 3)
        import_record = storage.record_snapshot(
            server_id,
            {
                "configId": None,
                "type": "import",
                "filePath": None,
                "fileName": original_name,
                "sizeBytes": 0,
                "durationSeconds": duration,
                "status": "success",
                "message": (
                    f"Imported world from {original_name} "
                    f"(layout={detection['layout']}, dirs={', '.join(produced)})"
                ),
                "safetySnapshotId": safety["id"],
                "mode": "import",
            },
        )
        progress.update(
            job_id,
            phase="done",
            import_record_id=import_record["id"],
            safety_snapshot_id=safety["id"],
            layout=detection["layout"],
            world_dirs=produced,
            duration_seconds=duration,
        )
    except Exception as exc:
        if progress.get(job_id).get("phase") not in ("done", "failed"):
            progress.update(job_id, phase="failed", error=str(exc))
        if was_running:
            _restart_server_safe(server, registry, job_id)
        raise
    else:
        if was_running:
            progress.update(job_id, phase="restarting")
            _restart_server_safe(server, registry, job_id)
        return import_record
    finally:
        if staging_root is not None and staging_root.exists():
            shutil.rmtree(staging_root, ignore_errors=True)
        archive_path.unlink(missing_ok=True)
        server_lock.release()


# ---------------------------------------------------------------------------
# Layout detection + normalization (pure, unit-testable)
# ---------------------------------------------------------------------------


def detect_world_layout(extract_root: Path) -> Dict[str, Any]:
    """Locate the world root under ``extract_root`` and classify its layout.

    Returns ``{"world_root": Path, "layout": "server"|"singleplayer"}``.

    The world root is the directory holding the shallowest ``level.dat``
    (most archives wrap the save in a single folder; some dump it at the
    root). A save is *singleplayer* when its Nether/End sit inside it as
    ``DIM-1`` / ``DIM1`` subdirectories; otherwise it is treated as a
    *server* world (the dimensions are separate ``_nether`` / ``_the_end``
    sibling dirs, or the world has no other dimensions yet).
    """
    world_root = _find_level_dat_dir(extract_root)
    if world_root is None:
        raise InvalidWorldArchiveError(
            "No level.dat found after extraction — not a Minecraft world"
        )

    has_dim = any((world_root / dim).is_dir() for dim in _SP_DIM_DIRS)
    layout = "singleplayer" if has_dim else "server"
    return {"world_root": world_root, "layout": layout}


def normalize_world(
    *,
    world_root: Path,
    layout: str,
    level_name: str,
    destination: Path,
) -> List[str]:
    """Materialise the server-format world dirs under ``destination``.

    Returns the list of produced directory names (e.g.
    ``["world", "world_nether", "world_the_end"]``). For ``server`` layout
    the source dirs are copied across and renamed to ``level_name``; for
    ``singleplayer`` the single save folder is split into the three server
    dimension dirs.
    """
    destination.mkdir(parents=True, exist_ok=True)
    produced: List[str] = []

    if layout == "singleplayer":
        # <L>/  ← save folder minus DIM-1/DIM1
        overworld = destination / level_name
        _copy_tree(
            world_root,
            overworld,
            exclude_names={d.lower() for d in _SP_DIM_DIRS},
        )
        produced.append(level_name)

        # <L>_nether/DIM-1/  ← save's DIM-1/
        nether_src = _child_dir(world_root, "DIM-1")
        if nether_src is not None:
            nether_dst = destination / f"{level_name}_nether" / "DIM-1"
            _copy_tree(nether_src, nether_dst)
            produced.append(f"{level_name}_nether")

        # <L>_the_end/DIM1/  ← save's DIM1/
        end_src = _child_dir(world_root, "DIM1")
        if end_src is not None:
            end_dst = destination / f"{level_name}_the_end" / "DIM1"
            _copy_tree(end_src, end_dst)
            produced.append(f"{level_name}_the_end")
        return produced

    # Server layout: copy the overworld and any sibling dimension dirs,
    # renaming the source level name to the target level name.
    src_name = world_root.name
    _copy_tree(world_root, destination / level_name)
    produced.append(level_name)

    if src_name:
        parent = world_root.parent
        for suffix in ("_nether", "_the_end"):
            sibling = _child_dir(parent, f"{src_name}{suffix}")
            if sibling is not None:
                _copy_tree(sibling, destination / f"{level_name}{suffix}")
                produced.append(f"{level_name}{suffix}")
    return produced


# ---------------------------------------------------------------------------
# Archive helpers
# ---------------------------------------------------------------------------


def _list_archive_names(path: Path) -> Tuple[str, List[str]]:
    """Return ``(kind, member_names)`` for a zip or tar archive."""
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as zf:
            return "zip", zf.namelist()
    if tarfile.is_tarfile(path):
        with tarfile.open(path, "r:*") as tf:
            return "tar", tf.getnames()
    raise InvalidWorldArchiveError(
        "Upload is not a readable .zip or .tar/.tar.gz archive"
    )


def _extract_upload(archive_path: Path, destination: Path) -> None:
    """Extract a user-uploaded zip/tar into ``destination`` (traversal-safe)."""
    if zipfile.is_zipfile(archive_path):
        with zipfile.ZipFile(archive_path) as zf:
            safe_extract_zip(zf, destination)
        return
    if tarfile.is_tarfile(archive_path):
        with tarfile.open(archive_path, "r:*") as tf:
            safe_extract_tar(tf, destination)
        return
    raise InvalidWorldArchiveError(
        "Upload is not a readable .zip or .tar/.tar.gz archive"
    )


def _find_level_dat_root(names: List[str]) -> Optional[str]:
    """Return the posix dir of the shallowest ``level.dat`` member, or None.

    ``""`` means the world sits at the archive root. Used for the cheap
    pre-extraction validation in the route.
    """
    best: Optional[str] = None
    best_depth = None
    for raw in names:
        name = raw.replace("\\", "/").strip("/")
        if name.rsplit("/", 1)[-1] != _LEVEL_DAT:
            continue
        parent = name[: -len(_LEVEL_DAT)].rstrip("/")
        depth = parent.count("/") if parent else -1
        if best_depth is None or depth < best_depth:
            best, best_depth = parent, depth
    return best


def _find_level_dat_dir(extract_root: Path) -> Optional[Path]:
    """Return the directory containing the shallowest ``level.dat`` on disk."""
    best: Optional[Path] = None
    best_depth: Optional[int] = None
    for level_dat in extract_root.rglob(_LEVEL_DAT):
        if not level_dat.is_file():
            continue
        parent = level_dat.parent
        depth = len(parent.relative_to(extract_root).parts)
        if best_depth is None or depth < best_depth:
            best, best_depth = parent, depth
    return best


def _child_dir(parent: Path, name: str) -> Optional[Path]:
    """Return ``parent/name`` if it exists as a directory (case-insensitive)."""
    direct = parent / name
    if direct.is_dir():
        return direct
    lowered = name.lower()
    for entry in parent.iterdir():
        if entry.is_dir() and entry.name.lower() == lowered:
            return entry
    return None


def _copy_tree(
    src: Path, dst: Path, *, exclude_names: Optional[set] = None
) -> None:
    """Copy ``src`` into ``dst``, optionally excluding top-level child names."""
    exclude = {n.lower() for n in (exclude_names or set())}
    dst.mkdir(parents=True, exist_ok=True)
    for entry in src.iterdir():
        if entry.name.lower() in exclude:
            continue
        target = dst / entry.name
        if entry.is_dir():
            shutil.copytree(entry, target, dirs_exist_ok=True)
        else:
            shutil.copy2(entry, target)


# ---------------------------------------------------------------------------
# Swap + safety + restart
# ---------------------------------------------------------------------------


def _swap_world_dirs(
    install_path: Path,
    normalized_root: Path,
    produced: List[str],
    server_id: str,
) -> None:
    """Replace the live world dirs with the normalized ones.

    Moves each existing target dir aside into a single ``.worldold-...``
    holding area, moves the new dirs in, then rmtrees the old on success.
    On any failure the moved-aside dirs are rolled back into place — the
    safety snapshot is the ultimate backstop, but we still avoid leaving a
    half-swapped world behind.
    """
    holding = install_path.parent / (
        f".worldold-{server_id}-"
        f"{time.strftime('%Y%m%d%H%M%S', time.gmtime())}-{uuid.uuid4().hex[:6]}"
    )
    holding.mkdir(parents=True, exist_ok=False)
    moved_aside: List[Tuple[str, Path]] = []
    moved_in: List[Path] = []
    try:
        for name in produced:
            live = install_path / name
            if live.exists():
                aside = holding / name
                os.replace(live, aside)
                moved_aside.append((name, aside))
            os.replace(normalized_root / name, install_path / name)
            moved_in.append(install_path / name)
    except OSError:
        # Roll back: remove anything we moved in, restore originals.
        for target in moved_in:
            shutil.rmtree(target, ignore_errors=True)
        for name, aside in moved_aside:
            try:
                os.replace(aside, install_path / name)
            except OSError:  # pragma: no cover - best effort
                pass
        raise
    finally:
        shutil.rmtree(holding, ignore_errors=True)


def _write_safety_snapshot(
    *,
    install_path: Path,
    storage_path: Path,
    server_id: str,
) -> Dict[str, Any]:
    """Build a pre-import safety tar of the live dir and record it."""
    timestamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
    final_path = storage_path / f"safety-import-{timestamp}.tar"
    if final_path.exists():
        final_path = storage_path / (
            f"safety-import-{timestamp}-{uuid.uuid4().hex[:6]}.tar"
        )

    tmp_path = storage_path / (final_path.name + ".partial")
    try:
        with tarfile.open(tmp_path, "w") as tf:
            for entry in sorted(install_path.iterdir()):
                # Don't pack the safety storage dir into itself.
                try:
                    if storage_path.resolve() == entry.resolve():
                        continue
                except OSError:
                    pass
                tf.add(entry, arcname=entry.name)
        os.replace(tmp_path, final_path)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise

    return storage.record_snapshot(
        server_id,
        {
            "configId": None,
            "type": "safety",
            "filePath": str(final_path),
            "fileName": final_path.name,
            "sizeBytes": final_path.stat().st_size,
            "durationSeconds": None,
            "status": "success",
            "message": "Pre-import safety snapshot",
        },
    )


def _record_error(server_id: str, start_time: float, *, message: str) -> None:
    """Best-effort error snapshot so the history table shows the attempt."""
    try:
        storage.record_snapshot(
            server_id,
            {
                "configId": None,
                "type": "import",
                "filePath": None,
                "fileName": None,
                "sizeBytes": 0,
                "durationSeconds": round(time.monotonic() - start_time, 3),
                "status": "error",
                "message": message,
                "mode": "import",
            },
        )
    except Exception:  # pragma: no cover - storage already broken
        pass


def _restart_server_safe(server: Dict[str, Any], registry, job_id: str) -> None:
    """Best-effort restart after an import that stopped the server."""
    try:
        result = registry.start_server(server)
        status = result.get("status")
        if status:
            server_storage.update_server_status(str(server["id"]), status)
    except Exception as exc:
        logger.warning("Failed to restart server post-import: %s", exc)
        progress.update(job_id, restart_error=str(exc))
