"""Backup orchestrator.

``run_backup(config_id, *, trigger="manual"|"scheduled")`` drives the
full sequence end-to-end and pushes phase updates into
:mod:`backend.backups.progress`. Critical decisions captured here:

- **Flush + confirm.** When ``cfg["flush"]`` is True and the server is
  running, send ``save-all flush`` and wait for the ``Saved the game``
  acknowledgement via :py:meth:`ServerManager.wait_for_log` (default
  60s). Timeout records a *warning* on the snapshot but does NOT abort
  — losing tail-end ticks of game state is preferable to refusing the
  scheduled backup outright.

- **Shutdown.** ``cfg["shutdown"]`` (or a flush failure) stops the
  server unconditionally before the staging copy. ``was_running`` is
  remembered so we restart at the end.

- **Hybrid compress.** The "skip world subdirectories from compression
  to avoid chunk corruption" rule in the brief is honoured by producing
  an *outer* uncompressed ``.tar`` containing two members:

  - ``data.tar.gz`` (gzip-compressed; everything except world dirs)
  - ``worlds.tar`` (uncompressed; the level dir from ``server.properties``
    plus its ``<level>_nether`` / ``<level>_the_end`` siblings)

  Restore extracts the outer tar and then each inner tar in turn — the
  on-disk layout after a restore is identical to ``compress=False``.

- **Atomic publish.** Archive is built under
  ``<storagePath>/.staging-<configId>-<ts>/`` and ``os.replace``'d into
  place. A crash during build leaves the previous archives untouched.

- **Retention.** ``cfg["maxSnapshots"] > 0`` slices the snapshot list
  for *this* config (not this server) by ``createdAt`` desc, unlinks the
  excess archive files and drops their records. Retention runs on
  manual AND scheduled runs (the brief was explicit on this). Ad-hoc
  backups (``config_id=None``) skip retention entirely.

The per-server RLock from :mod:`backend.server.locks` is held across
the whole run so a manual Start/Stop can't race the staging copy.
"""
from __future__ import annotations

import fnmatch
import logging
import os
import re
import shutil
import tarfile
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from backend.backups import progress, storage
from backend.server import storage as server_storage
from backend.server.locks import get_server_lock
from backend.server.registry import get_server_process_registry
from backend.utils.strings import slugify
from backend.utils.time import iso_z_now


logger = logging.getLogger(__name__)

_SAVED_GAME_RE = re.compile(r"Saved the game", re.IGNORECASE)
_FLUSH_WAIT_SECONDS = 60.0
_STOP_WAIT_SECONDS = 120.0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run_backup_async(config_id: str, *, trigger: str = "manual") -> str:
    """Spawn a daemon thread to run the backup; return its job_id."""
    job_id = progress.generate_job_id("bjb")
    progress.update(
        job_id,
        phase="starting",
        job_id=job_id,
        kind="backup",
        config_id=config_id,
        trigger=trigger,
    )

    def _runner() -> None:
        try:
            run_backup(config_id, trigger=trigger, job_id=job_id)
        except Exception as exc:  # pragma: no cover - belt and braces
            logger.exception("Unhandled error in backup worker")
            progress.update(job_id, phase="failed", error=str(exc))

    threading.Thread(
        target=_runner,
        name=f"backup-run-{config_id}",
        daemon=True,
    ).start()
    return job_id


def run_backup(
    config_id: str,
    *,
    trigger: str = "manual",
    job_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Run the full backup sequence for a saved config synchronously.

    Returns a snapshot record on success. On failure, records a
    failed-status snapshot entry (best-effort) and re-raises the
    exception so the worker thread can mark progress as failed.
    """
    if job_id is None:
        job_id = progress.generate_job_id("bjb")
        progress.update(
            job_id,
            phase="starting",
            job_id=job_id,
            kind="backup",
            config_id=config_id,
            trigger=trigger,
        )

    server_id = storage.lookup_server_for_config(config_id)
    if not server_id:
        progress.update(job_id, phase="failed", error="Config not found")
        raise ValueError(f"Backup config {config_id!r} not found")

    cfg = storage.get_config_record(server_id, config_id)
    if not cfg:
        progress.update(job_id, phase="failed", error="Config not found")
        raise ValueError(f"Backup config {config_id!r} not found")

    server = server_storage.get_server(server_id)
    if not server:
        progress.update(job_id, phase="failed", error="Server not found")
        raise ValueError(f"Server {server_id!r} not found")

    registry = get_server_process_registry()
    try:
        install_path = registry.resolve_install_path(server)
    except ValueError as exc:
        progress.update(job_id, phase="failed", error=str(exc))
        raise

    storage_path = storage.resolve_config_storage_path(cfg)

    return _execute_backup(
        server_id,
        server,
        cfg,
        storage_path,
        config_id=config_id,
        trigger=trigger,
        job_id=job_id,
    )


def run_adhoc_backup_async(
    server_id: str,
    *,
    storage_path_str: Optional[str] = None,
    compress: bool = True,
    flush: bool = True,
    shutdown: bool = False,
    trigger: str = "manual",
) -> str:
    """Spawn a daemon thread for an ad-hoc backup; return its job_id."""
    job_id = progress.generate_job_id("bjb")
    progress.update(
        job_id,
        phase="starting",
        job_id=job_id,
        kind="backup",
        config_id=None,
        trigger=trigger,
    )

    def _runner() -> None:
        try:
            run_adhoc_backup(
                server_id,
                storage_path_str=storage_path_str,
                compress=compress,
                flush=flush,
                shutdown=shutdown,
                trigger=trigger,
                job_id=job_id,
            )
        except Exception as exc:  # pragma: no cover - belt and braces
            logger.exception("Unhandled error in ad-hoc backup worker")
            progress.update(job_id, phase="failed", error=str(exc))

    threading.Thread(
        target=_runner,
        name=f"backup-adhoc-{server_id}",
        daemon=True,
    ).start()
    return job_id


def run_adhoc_backup(
    server_id: str,
    *,
    storage_path_str: Optional[str] = None,
    compress: bool = True,
    flush: bool = True,
    shutdown: bool = False,
    trigger: str = "manual",
    job_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Run a one-off backup with no pre-existing config synchronously.

    The snapshot is recorded with ``configId: null``. Retention is not
    applied — ad-hoc backups are managed manually by the user.
    ``storage_path_str=None`` falls back to ``<install_path>/backups``.
    """
    if job_id is None:
        job_id = progress.generate_job_id("bjb")
        progress.update(
            job_id,
            phase="starting",
            job_id=job_id,
            kind="backup",
            config_id=None,
            trigger=trigger,
        )

    server = server_storage.get_server(server_id)
    if not server:
        progress.update(job_id, phase="failed", error="Server not found")
        raise ValueError(f"Server {server_id!r} not found")

    registry = get_server_process_registry()
    try:
        install_path = registry.resolve_install_path(server)
    except ValueError as exc:
        progress.update(job_id, phase="failed", error=str(exc))
        raise

    storage_path = (
        Path(storage_path_str).expanduser().resolve()
        if storage_path_str
        else install_path / "backups"
    )

    # Synthetic cfg that satisfies all helpers (_build_archive uses
    # cfg['id'] directly for the staging dir name, so it must be set).
    cfg: Dict[str, Any] = {
        "id": job_id,
        "name": "manual",
        "compress": compress,
        "flush": flush,
        "shutdown": shutdown,
        "exclusions": [],
        "maxSnapshots": 0,
    }

    return _execute_backup(
        server_id,
        server,
        cfg,
        storage_path,
        config_id=None,
        trigger=trigger,
        job_id=job_id,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _execute_backup(
    server_id: str,
    server: Dict[str, Any],
    cfg: Dict[str, Any],
    storage_path: Path,
    *,
    config_id: Optional[str],
    trigger: str,
    job_id: str,
) -> Dict[str, Any]:
    """Core backup sequence: lock → flush/stop → archive → record → retain → restart.

    Both ``run_backup`` (config-based) and ``run_adhoc_backup`` (no config)
    delegate here. ``config_id=None`` skips retention and records the
    snapshot with a null configId.
    """
    storage_path.mkdir(parents=True, exist_ok=True)

    server_lock = get_server_lock(server_id)
    server_lock.acquire()
    start_time = time.monotonic()
    was_running = False
    warnings: List[str] = []
    registry = get_server_process_registry()
    try:
        was_running = _flush_and_maybe_stop(
            server_id, server, cfg, registry, job_id, warnings
        )
        archive_path, size_bytes = _build_archive(
            install_path=registry.resolve_install_path(server),
            storage_path=storage_path,
            cfg=cfg,
            server=server,
            job_id=job_id,
        )

        progress.update(job_id, phase="finalizing")
        duration = round(time.monotonic() - start_time, 3)
        snapshot = storage.record_snapshot(
            server_id,
            {
                "configId": config_id,
                "type": "backup",
                "filePath": str(archive_path),
                "fileName": archive_path.name,
                "sizeBytes": size_bytes,
                "durationSeconds": duration,
                "status": "warning" if warnings else "success",
                "message": "; ".join(warnings) if warnings else None,
                "trigger": trigger,
            },
        )

        if config_id is not None:
            _apply_retention(server_id, config_id, cfg)
    except Exception as exc:
        logger.exception("Backup failed for config %s", config_id)
        try:
            storage.record_snapshot(
                server_id,
                {
                    "configId": config_id,
                    "type": "backup",
                    "filePath": None,
                    "fileName": None,
                    "sizeBytes": 0,
                    "durationSeconds": round(time.monotonic() - start_time, 3),
                    "status": "error",
                    "message": str(exc),
                    "trigger": trigger,
                },
            )
        except Exception:  # pragma: no cover - storage already broken
            pass
        progress.update(job_id, phase="failed", error=str(exc))
        if was_running:
            _restart_server_safe(server, registry, job_id)
        raise
    else:
        if was_running:
            progress.update(job_id, phase="restarting")
            _restart_server_safe(server, registry, job_id)
        progress.update(
            job_id,
            phase="done",
            snapshot_id=snapshot["id"],
            size_bytes=size_bytes,
            duration_seconds=duration,
            warnings=warnings,
        )
        return snapshot
    finally:
        server_lock.release()


def _flush_and_maybe_stop(
    server_id: str,
    server: Dict[str, Any],
    cfg: Dict[str, Any],
    registry,
    job_id: str,
    warnings: List[str],
) -> bool:
    """Handle flush + optional shutdown. Returns ``was_running``."""
    runtime = registry.get_status(server_id) or {}
    running = runtime.get("status") == "running"

    if running and cfg.get("flush", True):
        progress.update(job_id, phase="flushing")
        send_result = registry.send_command(server_id, "save-all flush")
        if send_result.get("success"):
            manager = registry.get_manager(server_id)
            matched = False
            if manager is not None:
                matched = manager.wait_for_log(
                    _SAVED_GAME_RE, timeout=_FLUSH_WAIT_SECONDS
                )
            if not matched:
                warnings.append(
                    "Timed out waiting for 'Saved the game' confirmation"
                )
        else:
            warnings.append(
                f"save-all flush failed: {send_result.get('message')}"
            )

    if running and cfg.get("shutdown", False):
        progress.update(job_id, phase="stopping_server")
        stop_result = registry.stop_server(server_id)
        if stop_result.get("status") != "stopped":
            raise RuntimeError(
                f"Failed to stop server before backup: "
                f"{stop_result.get('message', 'unknown error')}"
            )
        server_storage.update_server_status(server_id, "stopped")
        return True

    return False


def _build_archive(
    *,
    install_path: Path,
    storage_path: Path,
    cfg: Dict[str, Any],
    server: Dict[str, Any],
    job_id: str,
) -> Tuple[Path, int]:
    """Stage a copy, build the tar(.gz), atomic-publish, return (path, size)."""
    timestamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
    config_slug = slugify(cfg.get("name") or "backup") or "backup"

    progress.update(job_id, phase="staging")
    exclusions = list(cfg.get("exclusions") or [])
    # Hide the in-archive ``backups`` dir so a future restore doesn't
    # nest archives recursively. The legacy route used the same guard.
    exclusions.append("backups/**")

    staging_root = storage_path / f".staging-{cfg['id']}-{timestamp}"
    if staging_root.exists():
        shutil.rmtree(staging_root, ignore_errors=True)
    staging_root.mkdir(parents=True, exist_ok=False)
    try:
        copy_root = staging_root / "tree"
        _copy_tree_with_exclusions(
            install_path, copy_root, exclusions
        )

        progress.update(job_id, phase="archiving")
        compress = bool(cfg.get("compress", True))
        archive_name = f"{config_slug}-{timestamp}.tar"
        staged_archive = staging_root / archive_name
        if compress:
            _write_hybrid_archive(copy_root, staged_archive, server)
        else:
            with tarfile.open(staged_archive, "w") as tf:
                _add_directory(tf, copy_root, arcname="")

        final_path = storage_path / archive_name
        # If an archive with this name somehow exists, atomic-publish
        # would replace it — that's surprising for the user. Bump the
        # name once with the job id rather than silently overwriting.
        if final_path.exists():
            final_path = storage_path / f"{config_slug}-{timestamp}-{job_id[-6:]}.tar"
        os.replace(staged_archive, final_path)
        size_bytes = final_path.stat().st_size
        return final_path, size_bytes
    finally:
        shutil.rmtree(staging_root, ignore_errors=True)


def _make_ignore(exclusions: List[str], install_root: Path) -> Callable:
    """Return a shutil.copytree ``ignore=`` callable matching ``exclusions``.

    Each pattern is matched against the path *relative to the install
    root*. Two semantics are supported:

    - **Glob pattern** (no ``**``): matched via :func:`fnmatch.fnmatchcase`
      against both the bare name and the rel-to-install path. Useful for
      file-name globs like ``*.log``.
    - **Subtree pattern** (``foo/**``, ``foo/bar/**``): a gitignore-style
      "everything under foo" form. We strip the trailing ``/**`` and
      treat the remainder as a directory prefix — the directory itself
      AND all of its descendants are excluded. This is the form callers
      reach for when they want to skip ``logs/`` or ``backups/`` whole.
    """
    glob_patterns: List[str] = []
    subtree_prefixes: List[str] = []
    for pat in exclusions:
        if not pat:
            continue
        if pat.endswith("/**"):
            subtree_prefixes.append(pat[:-3].rstrip("/"))
        elif pat.endswith("/*"):
            subtree_prefixes.append(pat[:-2].rstrip("/"))
        else:
            # Replace stray ``**`` with ``*`` so fnmatch doesn't choke on
            # the recursive form when callers use mid-pattern ``**``.
            glob_patterns.append(pat.replace("**", "*"))

    install_root_resolved = install_root.resolve()

    def _ignore(dirpath: str, names: List[str]) -> List[str]:
        ignored: List[str] = []
        dir_resolved = Path(dirpath).resolve()
        try:
            rel_dir = dir_resolved.relative_to(install_root_resolved)
        except ValueError:
            return ignored
        rel_dir_posix = rel_dir.as_posix()
        for name in names:
            rel = (
                f"{rel_dir_posix}/{name}".lstrip("./")
                if rel_dir_posix and rel_dir_posix != "."
                else name
            )
            excluded = False
            for prefix in subtree_prefixes:
                if rel == prefix or rel.startswith(prefix + "/"):
                    excluded = True
                    break
            if not excluded:
                for pat in glob_patterns:
                    if fnmatch.fnmatchcase(rel, pat) or fnmatch.fnmatchcase(
                        name, pat
                    ):
                        excluded = True
                        break
            if excluded:
                ignored.append(name)
        return ignored

    return _ignore


def _copy_tree_with_exclusions(
    src: Path, dst: Path, exclusions: List[str]
) -> None:
    """Mirror ``src`` to ``dst`` skipping anything matching ``exclusions``."""
    dst.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        src,
        dst,
        ignore=_make_ignore(exclusions, src),
        dirs_exist_ok=True,
        symlinks=False,
    )


def _add_directory(tf: tarfile.TarFile, src: Path, arcname: str) -> None:
    """Add every entry in ``src`` to ``tf`` under ``arcname``.

    We can't just call ``tf.add(src, arcname=arcname)`` and trust the
    default recursion because the staging tree may have moved between
    OS-level moves (Windows + atomic publish). Walking explicitly also
    means we keep the deterministic alphabetical ordering useful for
    reproducible-ish archives.
    """
    base = arcname.rstrip("/")
    for entry in sorted(src.rglob("*")):
        rel = entry.relative_to(src).as_posix()
        member = f"{base}/{rel}" if base else rel
        tf.add(entry, arcname=member, recursive=False)


def _level_dirs(server: Dict[str, Any]) -> List[str]:
    """Return the world directory names (level dir + nether/end siblings)."""
    raw_level = (server.get("levelName") or "world").strip() or "world"
    return [raw_level, f"{raw_level}_nether", f"{raw_level}_the_end"]


def _write_hybrid_archive(
    copy_root: Path, outer_path: Path, server: Dict[str, Any]
) -> None:
    """Build the hybrid ``outer.tar`` containing ``data.tar.gz`` + ``worlds.tar``.

    Worlds go into an uncompressed inner tar so the per-region chunk
    headers (already DEFLATE-compressed by Minecraft) aren't fed through
    gzip a second time. Everything else goes through gzip for the
    typical ~3x size reduction on configs and JARs.
    """
    world_dirs = {name.lower() for name in _level_dirs(server)}
    data_inner = outer_path.with_suffix(".data.tar.gz")
    worlds_inner = outer_path.with_suffix(".worlds.tar")

    try:
        with tarfile.open(data_inner, "w:gz") as tf:
            for entry in sorted(copy_root.iterdir()):
                if entry.is_dir() and entry.name.lower() in world_dirs:
                    continue
                tf.add(entry, arcname=entry.name)

        with tarfile.open(worlds_inner, "w") as tf:
            for entry in sorted(copy_root.iterdir()):
                if entry.is_dir() and entry.name.lower() in world_dirs:
                    tf.add(entry, arcname=entry.name)

        with tarfile.open(outer_path, "w") as tf:
            tf.add(data_inner, arcname="data.tar.gz")
            tf.add(worlds_inner, arcname="worlds.tar")
    finally:
        for tmp in (data_inner, worlds_inner):
            try:
                tmp.unlink()
            except OSError:
                pass


def _apply_retention(
    server_id: str, config_id: str, cfg: Dict[str, Any]
) -> None:
    """Trim snapshot history for ``config_id`` down to ``maxSnapshots``.

    Runs on every successful backup (manual + scheduled). Only deletes
    ``type == 'backup'`` snapshots; safety + restore records are
    preserved so the audit trail stays intact across cleanup.
    """
    max_snapshots = int(cfg.get("maxSnapshots") or 0)
    if max_snapshots <= 0:
        return

    snaps = [
        s for s in storage.list_snapshots(server_id, config_id=config_id)
        if s.get("type") == "backup"
    ]
    # list_snapshots already returns newest-first.
    for stale in snaps[max_snapshots:]:
        file_path = stale.get("filePath")
        if file_path:
            try:
                Path(file_path).unlink(missing_ok=True)
            except OSError:
                logger.warning("Failed to unlink %s during retention", file_path)
        storage.delete_snapshot_record(server_id, stale["id"])


def _restart_server_safe(server: Dict[str, Any], registry, job_id: str) -> None:
    """Best-effort restart after a backup that stopped the server."""
    try:
        result = registry.start_server(server)
        status = result.get("status")
        if status:
            server_storage.update_server_status(str(server["id"]), status)
    except Exception as exc:
        logger.warning("Failed to restart server post-backup: %s", exc)
        progress.update(job_id, restart_error=str(exc))
