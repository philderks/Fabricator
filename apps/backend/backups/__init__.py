"""Backup manager package.

Owns the full backup/restore stack: per-server config + history JSON
storage, the run-backup orchestrator (flush, optional shutdown, staged
copy with exclusions, hybrid compress, retention), the restore
orchestrator (mandatory safety snapshot + in-place/reset modes), the
APScheduler integration, and the Flask blueprint that exposes it all.

Public submodules:

- :mod:`backend.backups.storage`   — per-server JSON CRUD with atomic I/O.
- :mod:`backend.backups.progress`  — live job-status store for HTTP polling.
- :mod:`backend.backups.service`   — ``run_backup(config_id, *, trigger)``.
- :mod:`backend.backups.restore`   — ``run_restore(snapshot_id, *, mode)``.
- :mod:`backend.backups.scheduler` — APScheduler init + register/remove jobs.
- :mod:`backend.backups.routes`    — Flask blueprint ``backups_bp``.
"""
