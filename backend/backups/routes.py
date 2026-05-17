"""Flask routes for the backup manager.

All server-scoped routes live under ``/api/servers/<server_id>/...`` so
the per-server JSON file is trivially resolved without walking. The
``GET /api/backup-jobs/<job_id>`` endpoint is the only un-scoped route
(job ids are globally unique UUIDs; the polling caller knows the id but
not necessarily which server the job lives under).

Purge UX (no silent orphans).
-----------------------------

``DELETE /api/servers/<server_id>/backup-configs/<config_id>?purge=1``
deletes ONLY archive files that satisfy BOTH conditions:

1. The file's path is inside the config's ``storagePath`` (defensive —
   two configs sharing a storage dir must not delete each other's
   archives).
2. The file has a corresponding snapshot record under this config.

The response always reports ``deleted_files`` AND ``retained_paths`` so
the frontend can surface what was retained. When ``purge`` is unset the
files stay on disk; the frontend then shows the list of retained paths
in a follow-up banner. The brief is explicit on this: no silent orphans.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from flask import Blueprint, jsonify, request, send_file

from backend.backups import progress, restore, scheduler, service, storage
from backend.server.registry import get_server_process_registry
from backend.utils.routes import require_server
from backend.utils.strings import bool_from_str


logger = logging.getLogger(__name__)

backups_bp = Blueprint("backups", __name__, url_prefix="/api")


# ---------------------------------------------------------------------------
# Configs
# ---------------------------------------------------------------------------


@backups_bp.route("/servers/<server_id>/backup-configs", methods=["GET"])
@require_server
def list_backup_configs(server_id, server):
    configs = storage.list_configs(server_id)
    annotated = [_annotate_with_schedule(cfg) for cfg in configs]
    return jsonify(annotated)


@backups_bp.route("/servers/<server_id>/backup-configs", methods=["POST"])
@require_server
def create_backup_config(server_id, server):
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return jsonify({"error": "Request body must be a JSON object"}), 400

    error = _validate_config_payload(payload)
    if error:
        return jsonify({"error": error}), 400

    record = storage.create_config(server_id, payload)
    try:
        scheduler.register_job(record)
    except Exception as exc:
        logger.warning("Failed to register schedule for new config: %s", exc)
    return jsonify(_annotate_with_schedule(record)), 201


@backups_bp.route(
    "/servers/<server_id>/backup-configs/<config_id>", methods=["PUT"]
)
@require_server
def update_backup_config(server_id, server, config_id):
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return jsonify({"error": "Request body must be a JSON object"}), 400

    if not storage.get_config_record(server_id, config_id):
        return jsonify({"error": "Backup config not found"}), 404

    error = _validate_config_payload(payload, partial=True)
    if error:
        return jsonify({"error": error}), 400

    record = storage.update_config(server_id, config_id, payload)
    if not record:
        return jsonify({"error": "Backup config not found"}), 404
    try:
        scheduler.register_job(record)
    except Exception as exc:
        logger.warning("Failed to re-register schedule on update: %s", exc)
    return jsonify(_annotate_with_schedule(record))


@backups_bp.route(
    "/servers/<server_id>/backup-configs/<config_id>", methods=["DELETE"]
)
@require_server
def delete_backup_config(server_id, server, config_id):
    purge = bool_from_str(request.args.get("purge"))
    result = storage.delete_config(server_id, config_id)
    if result is None:
        return jsonify({"error": "Backup config not found"}), 404
    removed_config, removed_snapshots = result

    scheduler.remove_job(config_id)

    deleted, retained = _purge_archive_files(
        removed_config, removed_snapshots, purge
    )
    return jsonify(
        {
            "success": True,
            "config_id": config_id,
            "purge": bool(purge),
            "deleted_files": len(deleted),
            "deleted_paths": deleted,
            "retained_files": len(retained),
            "retained_paths": retained,
        }
    )


# ---------------------------------------------------------------------------
# Snapshots
# ---------------------------------------------------------------------------


@backups_bp.route("/servers/<server_id>/snapshots", methods=["GET"])
@require_server
def list_server_snapshots(server_id, server):
    snapshots = storage.list_snapshots(server_id)
    return jsonify(snapshots)


@backups_bp.route(
    "/servers/<server_id>/snapshots/<snapshot_id>", methods=["DELETE"]
)
@require_server
def delete_snapshot(server_id, server, snapshot_id):
    snapshot = storage.get_snapshot(server_id, snapshot_id)
    if not snapshot:
        return jsonify({"error": "Snapshot not found"}), 404

    file_path = snapshot.get("filePath")
    if file_path:
        try:
            Path(file_path).unlink(missing_ok=True)
        except OSError as exc:
            return jsonify(
                {"error": f"Failed to delete archive: {exc}"}
            ), 500

    storage.delete_snapshot_record(server_id, snapshot_id)
    return jsonify({"success": True})


@backups_bp.route(
    "/servers/<server_id>/snapshots/<snapshot_id>/download",
    methods=["GET"],
)
@require_server
def download_snapshot(server_id, server, snapshot_id):
    snapshot = storage.get_snapshot(server_id, snapshot_id)
    if not snapshot:
        return jsonify({"error": "Snapshot not found"}), 404
    file_path = snapshot.get("filePath")
    if not file_path or not Path(file_path).exists():
        return jsonify({"error": "Archive file not found on disk"}), 404
    return send_file(
        file_path,
        as_attachment=True,
        download_name=snapshot.get("fileName") or Path(file_path).name,
    )


# ---------------------------------------------------------------------------
# Summary + run + restore + job polling
# ---------------------------------------------------------------------------


@backups_bp.route("/servers/<server_id>/backup-summary", methods=["GET"])
@require_server
def backup_summary(server_id, server):
    snapshots = storage.list_snapshots(server_id)
    backup_snapshots = [s for s in snapshots if s.get("type") == "backup"]
    total_bytes = sum(int(s.get("sizeBytes") or 0) for s in backup_snapshots)
    last_snapshot = backup_snapshots[0] if backup_snapshots else None

    configs = storage.list_configs(server_id)
    next_runs: List[Dict[str, Any]] = []
    for cfg in configs:
        info = scheduler.get_job_info(cfg["id"])
        if info.get("next_run_time"):
            next_runs.append(
                {
                    "config_id": cfg["id"],
                    "config_name": cfg.get("name"),
                    "next_run_time": info["next_run_time"],
                }
            )
    next_runs.sort(key=lambda x: x["next_run_time"])
    next_run = next_runs[0] if next_runs else None

    try:
        registry = get_server_process_registry()
        install_path = registry.resolve_install_path(server)
        default_storage_path = str(install_path / "backups")
    except Exception:
        default_storage_path = None

    return jsonify(
        {
            "total_snapshots": len(backup_snapshots),
            "total_size_bytes": total_bytes,
            "last_snapshot": last_snapshot,
            "next_run": next_run,
            "configs_count": len(configs),
            "defaultStoragePath": default_storage_path,
        }
    )


@backups_bp.route(
    "/servers/<server_id>/backup-configs/<config_id>/run", methods=["POST"]
)
@require_server
def run_backup_now(server_id, server, config_id):
    if not storage.get_config_record(server_id, config_id):
        return jsonify({"error": "Backup config not found"}), 404
    job_id = service.run_backup_async(config_id, trigger="manual")
    return jsonify({"success": True, "job_id": job_id}), 202


@backups_bp.route("/servers/<server_id>/backup-quick", methods=["POST"])
@require_server
def run_quick_backup(server_id, server):
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return jsonify({"error": "Request body must be a JSON object"}), 400

    storage_path = (payload.get("storagePath") or "").strip() or None

    compress = bool(payload.get("compress", True))
    flush = bool(payload.get("flush", True))
    shutdown = bool(payload.get("shutdown", False))

    job_id = service.run_adhoc_backup_async(
        server_id,
        storage_path_str=storage_path,
        compress=compress,
        flush=flush,
        shutdown=shutdown,
        trigger="manual",
    )
    return jsonify({"success": True, "job_id": job_id}), 202


@backups_bp.route(
    "/servers/<server_id>/snapshots/<snapshot_id>/restore", methods=["POST"]
)
@require_server
def restore_snapshot(server_id, server, snapshot_id):
    payload = request.get_json(silent=True) or {}
    mode = (payload.get("mode") or "").strip()
    if mode not in restore.VALID_MODES:
        return jsonify(
            {
                "error": (
                    f"Invalid mode {mode!r}; expected one of "
                    f"{restore.VALID_MODES}"
                )
            }
        ), 400
    if not storage.get_snapshot(server_id, snapshot_id):
        return jsonify({"error": "Snapshot not found"}), 404
    try:
        job_id = restore.run_restore_async(snapshot_id, mode=mode)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"success": True, "job_id": job_id}), 202


@backups_bp.route("/backup-jobs/<job_id>", methods=["GET"])
def get_backup_job(job_id):
    payload = progress.get(job_id)
    if not payload:
        return jsonify({"error": "Job not found"}), 404
    return jsonify({"active": progress.is_active(job_id), **payload})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _annotate_with_schedule(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Attach the live next-fire time pulled from APScheduler."""
    job_info = scheduler.get_job_info(cfg["id"])
    enriched = dict(cfg)
    enriched["nextRunTime"] = job_info.get("next_run_time")
    return enriched


def _validate_config_payload(
    data: Dict[str, Any], *, partial: bool = False
) -> Optional[str]:
    """Return an error string if the payload is unusable.

    Required fields on create: ``name``, ``storagePath``. On update
    (``partial=True``) the same fields are validated only when present.
    """
    def _check_required(key: str) -> Optional[str]:
        value = data.get(key)
        if value is None or (isinstance(value, str) and not value.strip()):
            return f"Field '{key}' is required"
        return None

    if not partial:
        err = _check_required("name")
        if err:
            return err
    else:
        for key in ("name", "storagePath"):
            if key in data:
                value = data.get(key)
                if isinstance(value, str) and not value.strip():
                    return f"Field '{key}' must be a non-empty string"

    if "maxSnapshots" in data:
        try:
            n = int(data["maxSnapshots"])
            if n < 0:
                return "maxSnapshots must be >= 0"
        except (TypeError, ValueError):
            return "maxSnapshots must be an integer"

    schedule = data.get("schedule")
    if schedule is not None:
        if not isinstance(schedule, dict):
            return "schedule must be an object"
        if "frequencyHours" in schedule:
            try:
                freq = int(schedule["frequencyHours"])
                if freq <= 0:
                    return "schedule.frequencyHours must be > 0"
            except (TypeError, ValueError):
                return "schedule.frequencyHours must be an integer"

    return None


def _purge_archive_files(
    cfg: Dict[str, Any],
    snapshots: List[Dict[str, Any]],
    purge: bool,
) -> Tuple[List[str], List[str]]:
    """Return ``(deleted_paths, retained_paths)`` for a config-delete.

    When ``purge`` is False, every snapshot's archive file is retained
    so the caller (frontend) can show them in a follow-up banner.

    When ``purge`` is True, only files that live inside the config's
    ``storagePath`` are unlinked — defensive against two configs that
    happen to point at overlapping storage dirs.
    """
    storage_path_raw = (cfg.get("storagePath") or "").strip()
    storage_path = (
        Path(storage_path_raw).expanduser().resolve()
        if storage_path_raw else None
    )

    deleted: List[str] = []
    retained: List[str] = []
    for snap in snapshots:
        file_path_raw = snap.get("filePath")
        if not file_path_raw:
            continue
        file_path = Path(file_path_raw)
        if not file_path.exists():
            continue
        inside = (
            storage_path is not None
            and _is_within(file_path.resolve(), storage_path)
        )
        if purge and inside:
            try:
                file_path.unlink()
                deleted.append(str(file_path))
            except OSError as exc:
                logger.warning("Failed to unlink %s: %s", file_path, exc)
                retained.append(str(file_path))
        else:
            retained.append(str(file_path))
    return deleted, retained


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False
