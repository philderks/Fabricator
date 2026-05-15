"""APScheduler integration for scheduled backups.

One module-level :class:`flask_apscheduler.APScheduler` instance backs the
whole package. :func:`init_scheduler` is idempotent (safe under
Werkzeug's debug-reload AND ``create_app()`` being called more than once
in tests) and honours ``FABRICATOR_DISABLE_SCHEDULER=1`` for the pytest
suite — background timers leaking across tests caused exactly this kind
of flake before.

Job IDs are stable: ``f"backup-{config_id}"``. Combined with
``replace_existing=True`` the second registration of the same config
just rewrites the trigger, so a double-init is harmless rather than
raising ``ConflictingIdError``.

Trigger choice:

- ``frequencyHours == 24`` → :class:`CronTrigger` parsed from
  ``timeOfDay`` ("HH:MM"). Once-a-day fires deserve cron semantics so
  DST shifts and clock skew don't drift them forward.
- Otherwise → :class:`IntervalTrigger` aligned to the configured
  ``timeOfDay`` for its ``start_date``. Interval triggers handle the
  "every N hours" sub-daily case cleanly.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, time as dtime, timedelta, timezone
from typing import Any, Dict, Optional

from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from flask_apscheduler import APScheduler


logger = logging.getLogger(__name__)

scheduler = APScheduler()
_initialised = False


def _is_disabled() -> bool:
    return os.environ.get("FABRICATOR_DISABLE_SCHEDULER", "").strip() == "1"


def init_scheduler(app) -> None:
    """Initialise the APScheduler instance and register every job.

    Idempotent across re-invocation:

    - ``scheduler.init_app(app)`` is only called when the scheduler has
      not yet been bound to an app (the underlying APScheduler
      otherwise raises on rebind).
    - ``scheduler.start()`` is guarded by ``scheduler.running``.
    - Job registration uses ``replace_existing=True`` so an already-known
      ``job_id`` is rewritten rather than raising ``ConflictingIdError``.

    Honours ``FABRICATOR_DISABLE_SCHEDULER=1``: no init, no start, no
    job registration. The env-gate is the test suite's only line of
    defence against APScheduler background timers leaking across
    monkeypatched configs.
    """
    global _initialised

    if _is_disabled():
        logger.info("Backup scheduler disabled by FABRICATOR_DISABLE_SCHEDULER=1")
        return

    if not _initialised:
        scheduler.init_app(app)
        _initialised = True

    if not scheduler.running:
        scheduler.start()

    register_all_jobs()


def register_all_jobs() -> None:
    """(Re-)register every backup config that has ``schedule.enabled``.

    Called once from :func:`init_scheduler` on startup. Safe to call
    again at runtime — ``replace_existing=True`` makes each call a no-op
    for unchanged configs and a rewrite for changed ones.
    """
    if _is_disabled() or not _initialised:
        return
    # Local import to avoid an import-cycle in tests that import
    # scheduler before the package has fully initialised.
    from backend.backups import storage

    for cfg in storage.all_configs():
        try:
            register_job(cfg)
        except Exception as exc:
            logger.warning(
                "Failed to register backup schedule for %s: %s",
                cfg.get("id"), exc,
            )


def register_job(cfg: Dict[str, Any]) -> Optional[str]:
    """Register / replace the scheduler job for ``cfg``.

    Returns the job id, or ``None`` if the config has no enabled
    schedule (in which case any pre-existing job is removed so a
    schedule toggled OFF disappears immediately).
    """
    if _is_disabled() or not _initialised:
        return None

    config_id = cfg.get("id")
    if not config_id:
        return None
    job_id = f"backup-{config_id}"

    schedule = cfg.get("schedule") or {}
    enabled = bool(schedule.get("enabled", False))
    if not enabled:
        remove_job(config_id)
        return None

    trigger = _build_trigger(schedule)
    scheduler.add_job(
        id=job_id,
        func="backend.backups.scheduler:_run_scheduled_backup",
        args=[config_id],
        trigger=trigger,
        replace_existing=True,
        misfire_grace_time=3600,
    )
    return job_id


def remove_job(config_id: str) -> bool:
    """Remove the job for ``config_id``. Returns True iff something was removed."""
    if not _initialised or _is_disabled():
        return False
    job_id = f"backup-{config_id}"
    try:
        scheduler.remove_job(job_id)
        return True
    except Exception:
        # APScheduler raises JobLookupError for unknown ids; we don't
        # want to leak that exact type up to callers.
        return False


def get_job_info(config_id: str) -> Dict[str, Any]:
    """Return ``{ next_run_time, job_id }`` for the config's job, or ``{}``."""
    if not _initialised or _is_disabled():
        return {}
    job_id = f"backup-{config_id}"
    try:
        job = scheduler.get_job(job_id)
    except Exception:
        return {}
    if not job:
        return {}
    next_run = job.next_run_time
    return {
        "job_id": job.id,
        "next_run_time": (
            next_run.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
            if next_run is not None else None
        ),
    }


def reset_for_tests() -> None:
    """Shut the scheduler down and drop all jobs. Tests only."""
    global _initialised
    try:
        if scheduler.running:
            scheduler.shutdown(wait=False)
    except Exception:
        pass
    try:
        scheduler.remove_all_jobs()
    except Exception:
        pass
    _initialised = False


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------


def _parse_time_of_day(value: str | None) -> dtime:
    """Parse ``"HH:MM"`` (or ``"HH"``) → :class:`datetime.time`.

    Falls back to ``03:00`` when the value is missing or unparseable
    rather than refusing to register a schedule outright — the config UI
    validates this server-side, so a bad value here is almost certainly
    a hand-edited JSON file.
    """
    raw = (value or "").strip()
    if not raw:
        return dtime(hour=3, minute=0)
    parts = raw.split(":")
    try:
        hour = int(parts[0])
        minute = int(parts[1]) if len(parts) > 1 else 0
    except ValueError:
        return dtime(hour=3, minute=0)
    hour = max(0, min(23, hour))
    minute = max(0, min(59, minute))
    return dtime(hour=hour, minute=minute)


def _build_trigger(schedule: Dict[str, Any]):
    """Build the APScheduler trigger from a config's ``schedule`` block."""
    frequency_hours = int(schedule.get("frequencyHours") or 24)
    time_of_day = _parse_time_of_day(schedule.get("timeOfDay"))

    if frequency_hours == 24:
        return CronTrigger(hour=time_of_day.hour, minute=time_of_day.minute)

    # IntervalTrigger anchored at the next occurrence of ``timeOfDay``
    # so "every 6h at :30" still feels predictable from the user's PoV.
    now = datetime.now(timezone.utc)
    anchor = now.replace(
        hour=time_of_day.hour,
        minute=time_of_day.minute,
        second=0,
        microsecond=0,
    )
    if anchor <= now:
        anchor = anchor + timedelta(hours=frequency_hours)
    return IntervalTrigger(hours=frequency_hours, start_date=anchor)


def _run_scheduled_backup(config_id: str) -> None:
    """Entry point APScheduler calls. Delegates to the service layer.

    Kept in this module (rather than in service.py) so the trigger's
    ``func`` reference is a stable importable path. Importing
    :mod:`backend.backups.service` lazily avoids an import cycle at
    blueprint registration time.
    """
    from backend.backups import service

    try:
        service.run_backup(config_id, trigger="scheduled")
    except Exception:
        logger.exception(
            "Scheduled backup failed for config %s", config_id
        )
