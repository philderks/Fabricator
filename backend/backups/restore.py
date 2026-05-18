"""Restore orchestrator.

``run_restore(snapshot_id, *, mode)`` runs the sequence:

1. Stop the server (unconditionally — even when ``cfg["flush"]`` would
   be safe for normal backups, restore mutates the live tree).
2. **Mandatory safety snapshot.** Fast uncompressed ``.tar`` of the live
   server dir into the *owning config's* ``storagePath`` named
   ``safety-<configSlug>-<ts>.tar``. Recorded with ``type="safety"``.
   If this step raises ANY exception the entire restore aborts, the
   live dir is NEVER touched, and the server is restarted if it was
   running. Non-negotiable per the brief and pinned by a dedicated test.
3. Extract the chosen snapshot into a staging area, then:

   - **in_place** — copy/overwrite from staging onto the live dir. Files
     only in the live dir are preserved (overlay semantics).
   - **reset**    — atomic-swap (rename live → ``.old-...``, replace
     with staging, ``shutil.rmtree`` the old dir).

4. Record a ``type="restore"`` snapshot row with a message describing
   the mode.
5. Restart the server if it was running before step 1.

Hybrid archives (the ``data.tar.gz`` + ``worlds.tar`` produced by
``compress=True`` backups) are detected by membership and each inner
tar is extracted in turn. Plain ``.tar`` (compress=False) and the
``.tar.gz`` shorthand also work.
"""
from __future__ import annotations

import logging
import os
import shutil
import tarfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.backups import progress, storage
from backend.server import storage as server_storage
from backend.server.locks import get_server_lock
from backend.server.registry import get_server_process_registry
from backend.utils.strings import slugify
from backend.utils.zip import safe_extract_tar


logger = logging.getLogger(__name__)

VALID_MODES = ("in_place", "reset")


def run_restore_async(snapshot_id: str, *, mode: str) -> str:
    """Spawn a daemon thread to run the restore; return its job_id.

    Raises :class:`ValueError` synchronously if ``mode`` is unknown or
    the snapshot can't be found — the route layer surfaces these as 4xx
    rather than failing silently in the background thread.
    """
    if mode not in VALID_MODES:
        raise ValueError(
            f"Invalid restore mode {mode!r}; expected one of {VALID_MODES}"
        )
    server_id = storage.lookup_server_for_snapshot(snapshot_id)
    if not server_id:
        raise ValueError(f"Snapshot {snapshot_id!r} not found")

    job_id = progress.generate_job_id("bjr")
    progress.update(
        job_id,
        phase="starting",
        job_id=job_id,
        kind="restore",
        snapshot_id=snapshot_id,
        mode=mode,
    )

    def _runner() -> None:
        try:
            run_restore(snapshot_id, mode=mode, job_id=job_id)
        except Exception as exc:  # pragma: no cover - belt and braces
            logger.exception("Unhandled error in restore worker")
            progress.update(job_id, phase="failed", error=str(exc))

    threading.Thread(
        target=_runner,
        name=f"backup-restore-{snapshot_id}",
        daemon=True,
    ).start()
    return job_id


def run_restore(
    snapshot_id: str,
    *,
    mode: str,
    job_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Run the full restore sequence synchronously.

    Returns the ``type="restore"`` snapshot record on success. On
    failure, records an error-status restore snapshot (best-effort),
    restarts the server if it was originally running, and re-raises.
    """
    if mode not in VALID_MODES:
        raise ValueError(f"Invalid restore mode {mode!r}")
    if job_id is None:
        job_id = progress.generate_job_id("bjr")
        progress.update(
            job_id,
            phase="starting",
            job_id=job_id,
            kind="restore",
            snapshot_id=snapshot_id,
            mode=mode,
        )

    server_id = storage.lookup_server_for_snapshot(snapshot_id)
    if not server_id:
        progress.update(job_id, phase="failed", error="Snapshot not found")
        raise ValueError(f"Snapshot {snapshot_id!r} not found")

    snapshot = storage.get_snapshot(server_id, snapshot_id)
    if not snapshot:
        progress.update(job_id, phase="failed", error="Snapshot not found")
        raise ValueError(f"Snapshot {snapshot_id!r} not found")

    archive_path_raw = snapshot.get("filePath")
    if not archive_path_raw:
        progress.update(job_id, phase="failed", error="Snapshot has no file")
        raise ValueError(f"Snapshot {snapshot_id!r} has no associated file")
    archive_path = Path(archive_path_raw)
    if not archive_path.exists():
        progress.update(job_id, phase="failed", error="Archive missing on disk")
        raise FileNotFoundError(
            f"Archive {archive_path} no longer exists on disk"
        )

    cfg = storage.get_config_record(server_id, snapshot.get("configId") or "")
    if not cfg:
        progress.update(
            job_id,
            phase="failed",
            error="Owning backup config not found (cannot place safety snapshot)",
        )
        raise ValueError(
            "Owning backup config not found — restore aborted because the "
            "mandatory safety snapshot has no storage path"
        )

    server = server_storage.get_server(server_id)
    if not server:
        progress.update(job_id, phase="failed", error="Server not found")
        raise ValueError(f"Server {server_id!r} not found")

    registry = get_server_process_registry()
    install_path = registry.resolve_install_path(server)
    safety_storage = storage.resolve_config_storage_path(cfg)
    safety_storage.mkdir(parents=True, exist_ok=True)

    server_lock = get_server_lock(server_id)
    server_lock.acquire()
    start_time = time.monotonic()
    was_running = False
    try:
        runtime = registry.get_status(server_id) or {}
        was_running = runtime.get("status") == "running"
        if was_running:
            progress.update(job_id, phase="stopping_server")
            stop_result = registry.stop_server(server_id)
            if stop_result.get("status") != "stopped":
                raise RuntimeError(
                    f"Failed to stop server before restore: "
                    f"{stop_result.get('message', 'unknown error')}"
                )
            server_storage.update_server_status(server_id, "stopped")

        # MANDATORY safety snapshot — any exception here aborts the
        # restore BEFORE we touch the live tree.
        progress.update(job_id, phase="safety_snapshot")
        try:
            safety = _write_safety_snapshot(
                install_path=install_path,
                cfg=cfg,
                storage_path=safety_storage,
                server_id=server_id,
            )
        except Exception as exc:
            logger.exception("Safety snapshot failed — aborting restore")
            progress.update(
                job_id,
                phase="failed",
                error=f"Safety snapshot failed: {exc}",
            )
            if was_running:
                _restart_server_safe(server, registry, job_id)
            # Best-effort error record so the UI's history table shows
            # the attempt and the failure reason. Note: NOT recording a
            # type=safety record (it failed) — only the error trail.
            try:
                storage.record_snapshot(
                    server_id,
                    {
                        "configId": snapshot.get("configId"),
                        "type": "restore",
                        "filePath": None,
                        "fileName": None,
                        "sizeBytes": 0,
                        "durationSeconds": round(
                            time.monotonic() - start_time, 3
                        ),
                        "status": "error",
                        "message": f"Safety snapshot failed: {exc}",
                        "sourceSnapshotId": snapshot_id,
                        "mode": mode,
                    },
                )
            except Exception:  # pragma: no cover - storage already broken
                pass
            raise

        # Stage the archive contents.
        progress.update(job_id, phase="extracting")
        staging_root = install_path.parent / (
            f".restore-{server_id}-{time.strftime('%Y%m%d%H%M%S', time.gmtime())}-{uuid.uuid4().hex[:6]}"
        )
        if staging_root.exists():
            shutil.rmtree(staging_root, ignore_errors=True)
        staging_root.mkdir(parents=True, exist_ok=False)
        try:
            _extract_archive(archive_path, staging_root)

            if mode == "in_place":
                progress.update(job_id, phase="overlaying")
                _overlay_copy(staging_root, install_path)
            else:
                progress.update(job_id, phase="swapping")
                _atomic_swap(install_path, staging_root, server_id)
        finally:
            if staging_root.exists():
                shutil.rmtree(staging_root, ignore_errors=True)

        duration = round(time.monotonic() - start_time, 3)
        restore_record = storage.record_snapshot(
            server_id,
            {
                "configId": snapshot.get("configId"),
                "type": "restore",
                "filePath": None,
                "fileName": None,
                "sizeBytes": snapshot.get("sizeBytes") or 0,
                "durationSeconds": duration,
                "status": "success",
                "message": f"Restored from {archive_path.name} (mode={mode})",
                "sourceSnapshotId": snapshot_id,
                "safetySnapshotId": safety["id"],
                "mode": mode,
            },
        )
        progress.update(
            job_id,
            phase="done",
            restore_record_id=restore_record["id"],
            safety_snapshot_id=safety["id"],
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
        return restore_record
    finally:
        server_lock.release()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------



def _write_safety_snapshot(
    *,
    install_path: Path,
    cfg: Dict[str, Any],
    storage_path: Path,
    server_id: str,
) -> Dict[str, Any]:
    """Build the mandatory safety tar and return its snapshot record."""
    timestamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
    config_slug = slugify(cfg.get("name") or "backup") or "backup"
    safety_name = f"safety-{config_slug}-{timestamp}.tar"
    final_path = storage_path / safety_name
    # If a previous safety with the same name exists (very unlikely —
    # second-resolution timestamp + UUID slug), bump the name once.
    if final_path.exists():
        final_path = storage_path / (
            f"safety-{config_slug}-{timestamp}-{uuid.uuid4().hex[:6]}.tar"
        )

    tmp_path = storage_path / (final_path.name + ".partial")
    try:
        with tarfile.open(tmp_path, "w") as tf:
            for entry in sorted(install_path.iterdir()):
                # Skip the storage dir if it lives inside the install
                # tree — recursively packing the backups folder into the
                # safety would grow with every restore.
                try:
                    entry_resolved = entry.resolve()
                    if storage_path.resolve() == entry_resolved:
                        continue
                except OSError:
                    pass
                tf.add(entry, arcname=entry.name)
        os.replace(tmp_path, final_path)
    except Exception:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise

    return storage.record_snapshot(
        server_id,
        {
            "configId": cfg.get("id"),
            "type": "safety",
            "filePath": str(final_path),
            "fileName": final_path.name,
            "sizeBytes": final_path.stat().st_size,
            "durationSeconds": None,
            "status": "success",
            "message": "Pre-restore safety snapshot",
        },
    )


def _extract_archive(archive_path: Path, destination: Path) -> None:
    """Extract a backup archive (plain tar, tar.gz, or hybrid outer tar)."""
    with tarfile.open(archive_path, "r:*") as outer:
        names = set(outer.getnames())
        if {"data.tar.gz", "worlds.tar"}.issubset(names):
            # Hybrid layout produced by service.py compress=True.
            outer.extractall(destination, members=_filtered_outer_members(outer))
            data_inner = destination / "data.tar.gz"
            worlds_inner = destination / "worlds.tar"
            with tarfile.open(data_inner, "r:gz") as tf:
                safe_extract_tar(tf, destination)
            with tarfile.open(worlds_inner, "r") as tf:
                safe_extract_tar(tf, destination)
            try:
                data_inner.unlink()
            except OSError:
                pass
            try:
                worlds_inner.unlink()
            except OSError:
                pass
            return

        # Plain tar (compress=False) or tar.gz — extract directly.
        # Reopen because extractall consumes the iterator state in some
        # Python versions when we already inspected getnames().
    with tarfile.open(archive_path, "r:*") as tf:
        safe_extract_tar(tf, destination)


def _filtered_outer_members(tf: tarfile.TarFile) -> List[tarfile.TarInfo]:
    """Return only the two inner-tar entries from the hybrid outer."""
    wanted = {"data.tar.gz", "worlds.tar"}
    members = []
    for m in tf.getmembers():
        if m.name in wanted and m.isfile():
            members.append(m)
    return members


def _overlay_copy(src: Path, dst: Path) -> None:
    """Copy every file from ``src`` over ``dst``, preserving extra dst files.

    Used by mode=in_place. Files that exist in dst but not src are left
    in place — matches the brief's "overlay" semantics.
    """
    for entry in src.rglob("*"):
        rel = entry.relative_to(src)
        target = dst / rel
        if entry.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(entry, target)


def _atomic_swap(install_path: Path, staging: Path, server_id: str) -> None:
    """Rename live → ``.old-...``, replace with staging, ``rmtree`` old.

    Mirrors the legacy ``restore_server_backup`` swap dance.
    """
    parent = install_path.parent
    old_dir = parent / (
        f".old-{server_id}-{time.strftime('%Y%m%d%H%M%S', time.gmtime())}-{uuid.uuid4().hex[:6]}"
    )
    os.replace(install_path, old_dir)
    try:
        os.replace(staging, install_path)
    except OSError:
        # Roll back: bring the live dir back into place so we don't
        # leave the server pointing at a missing path.
        try:
            os.replace(old_dir, install_path)
        except OSError:
            pass
        raise
    shutil.rmtree(old_dir, ignore_errors=True)


def _restart_server_safe(server: Dict[str, Any], registry, job_id: str) -> None:
    """Best-effort restart after a restore that stopped the server."""
    try:
        result = registry.start_server(server)
        status = result.get("status")
        if status:
            server_storage.update_server_status(str(server["id"]), status)
    except Exception as exc:
        logger.warning("Failed to restart server post-restore: %s", exc)
        progress.update(job_id, restart_error=str(exc))
