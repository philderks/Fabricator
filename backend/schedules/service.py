"""Scheduled commands: validation, APScheduler jobs and the step runner.

Schedules live on the server record (``server["schedules"]``), so
:func:`backend.server.storage.update_server` gives us atomic writes and a
server delete drops them with the record. Jobs reuse the backup package's
APScheduler instance (one scheduler per process) under the id
``cmd-<schedule_id>``; like backups they are rebuilt from JSON at boot.

Record shape::

    {
      "id": "sch_...",
      "name": "Daily restart",
      "enabled": true,
      "timezone": "Europe/Amsterdam",
      "trigger": {"type": "interval", "minutes": 30}
               | {"type": "daily", "time": "04:00", "days": ["mon", "fri"]}
               | {"type": "cron", "expression": "0 4 * * sun"},
      "steps": [
        {"action": "command", "command": "say Restarting", "delaySeconds": 0},
        {"action": "restart", "delaySeconds": 300}
      ]
    }

``days: []`` means every day. ``delaySeconds`` is the wait *before* a step.
"""
from __future__ import annotations

import logging
import re
import threading
import time
import uuid
from datetime import timezone
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from backend.backups import scheduler as sched_mod
from backend.server import storage
from backend.server.java_compat import resolve_required_java, skip_java_enforcement
from backend.server.locks import get_server_lock
from backend.server.registry import get_server_process_registry
from backend.utils.time import iso_z_now


logger = logging.getLogger(__name__)

ACTIONS = ("command", "start", "stop", "restart")
DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
MAX_STEPS = 20
MAX_DELAY_SECONDS = 3600
MAX_INTERVAL_MINUTES = 7 * 24 * 60
MAX_COMMAND_LENGTH = 1000

_HHMM = re.compile(r"([01]\d|2[0-3]):[0-5]\d")

# Serialises read-modify-write of server["schedules"] and the matching job
# change, so two concurrent edits can't leave the job on the older version.
_write_lock = threading.Lock()
# ponytail: last run is in-memory only and resets on panel restart; persist it if users ask.
_last_runs: Dict[str, Dict[str, Any]] = {}


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate(data: Any) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Return ``(clean, None)`` for a usable create/update body, else ``(None, error)``."""
    if not isinstance(data, dict):
        return None, "Request body must be a JSON object"

    name = data.get("name")
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 100:
        return None, "name must be 1-100 characters"

    enabled = data.get("enabled", True)
    if not isinstance(enabled, bool):
        return None, "enabled must be a boolean"

    # Empty falls back to the host zone, as for backup schedules.
    tz = data.get("timezone") or ""
    if not isinstance(tz, str):
        return None, "timezone must be a string"
    if tz:
        try:
            ZoneInfo(tz)
        except (ZoneInfoNotFoundError, ValueError):
            return None, f"timezone '{tz}' is not a valid IANA time zone"

    trigger, error = _clean_trigger(data.get("trigger"))
    if error:
        return None, error
    steps, error = _clean_steps(data.get("steps"))
    if error:
        return None, error

    clean = {
        "name": name.strip(),
        "enabled": enabled,
        "timezone": tz,
        "trigger": trigger,
        "steps": steps,
    }
    try:
        _build_trigger(clean)
    except ValueError as exc:
        return None, f"Invalid schedule: {exc}"
    return clean, None


def _int_in(value: Any, low: int, high: int) -> Optional[int]:
    """``value`` if it is an int in ``[low, high]``, else None. Bools are
    rejected: ``True`` is an int and would pass as 1."""
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if low <= value <= high else None


def _clean_trigger(trigger: Any) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    if not isinstance(trigger, dict):
        return None, "trigger must be an object"
    kind = trigger.get("type")

    if kind == "interval":
        minutes = _int_in(trigger.get("minutes"), 1, MAX_INTERVAL_MINUTES)
        if minutes is None:
            return None, f"trigger.minutes must be an integer from 1 to {MAX_INTERVAL_MINUTES}"
        return {"type": "interval", "minutes": minutes}, None

    if kind == "daily":
        at = trigger.get("time")
        if not isinstance(at, str) or not _HHMM.fullmatch(at):
            return None, "trigger.time must be HH:MM"
        days = trigger.get("days") or []
        if not isinstance(days, list) or any(day not in DAYS for day in days):
            return None, "trigger.days must be a list of mon, tue, wed, thu, fri, sat, sun"
        return {"type": "daily", "time": at, "days": [d for d in DAYS if d in days]}, None

    if kind == "cron":
        expression = trigger.get("expression")
        fields = expression.split() if isinstance(expression, str) else []
        if len(fields) != 5:
            return None, "trigger.expression must be a 5-field cron expression"
        # Two places APScheduler 3 silently disagrees with crontab. It counts
        # weekdays from Monday=0, not Sunday=0, so "0 4 * * 0" (and the */2
        # step) land on different days; names mean the same in both. And it
        # ANDs day-of-month with day-of-week where crontab ORs them.
        if re.search(r"\d", fields[4]):
            return None, "Use day names (mon-sun) in the cron day-of-week field"
        if fields[2] != "*" and fields[4] != "*":
            return None, "Restrict day of month or day of week in a cron expression, not both"
        return {"type": "cron", "expression": " ".join(fields)}, None

    return None, "trigger.type must be interval, daily or cron"


def _clean_steps(steps: Any) -> Tuple[Optional[List[Dict[str, Any]]], Optional[str]]:
    if not isinstance(steps, list) or not 1 <= len(steps) <= MAX_STEPS:
        return None, f"steps must be a list of 1 to {MAX_STEPS} steps"

    clean = []
    for i, step in enumerate(steps, 1):
        if not isinstance(step, dict) or step.get("action") not in ACTIONS:
            return None, f"Step {i}: action must be one of {', '.join(ACTIONS)}"
        delay = _int_in(step.get("delaySeconds", 0), 0, MAX_DELAY_SECONDS)
        if delay is None:
            return None, f"Step {i}: delaySeconds must be an integer from 0 to {MAX_DELAY_SECONDS}"
        item = {"action": step["action"], "delaySeconds": delay}

        if step["action"] == "command":
            command = step.get("command")
            command = command.strip() if isinstance(command, str) else ""
            if not 1 <= len(command) <= MAX_COMMAND_LENGTH:
                return None, f"Step {i}: command must be 1-{MAX_COMMAND_LENGTH} characters"
            # send_command only strips the ends; an embedded newline would
            # reach the console as a second, unvalidated command.
            if "\n" in command or "\r" in command:
                return None, f"Step {i}: command must be a single line"
            item["command"] = command
        clean.append(item)
    return clean, None


def _build_trigger(schedule: Dict[str, Any]):
    tz = sched_mod._resolve_timezone(schedule)
    trigger = schedule["trigger"]
    if trigger["type"] == "interval":
        return IntervalTrigger(minutes=trigger["minutes"], timezone=tz)
    if trigger["type"] == "daily":
        at = sched_mod._parse_time_of_day(trigger["time"])
        return CronTrigger(
            hour=at.hour,
            minute=at.minute,
            day_of_week=",".join(trigger["days"]) or "*",
            timezone=tz,
        )
    return CronTrigger.from_crontab(trigger["expression"], timezone=tz)


# ---------------------------------------------------------------------------
# Storage (on the server record)
# ---------------------------------------------------------------------------


def _schedules_of(server_id: str) -> List[Dict[str, Any]]:
    server = storage.get_server(server_id) or {}
    return list(server.get("schedules") or [])


def get_schedule(server_id: str, schedule_id: str) -> Optional[Dict[str, Any]]:
    return next((s for s in _schedules_of(server_id) if s.get("id") == schedule_id), None)


def list_schedules(server: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [_annotate(s) for s in server.get("schedules") or []]


def create_schedule(server_id: str, clean: Dict[str, Any]) -> Dict[str, Any]:
    schedule = {"id": f"sch_{uuid.uuid4().hex[:10]}", **clean}
    with _write_lock:
        schedules = _schedules_of(server_id)
        schedules.append(schedule)
        storage.update_server(server_id, {"schedules": schedules})
        register_job(server_id, schedule)
    return _annotate(schedule)


def update_schedule(
    server_id: str, schedule_id: str, clean: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    schedule = {"id": schedule_id, **clean}
    with _write_lock:
        schedules = _schedules_of(server_id)
        index = next((i for i, s in enumerate(schedules) if s.get("id") == schedule_id), None)
        if index is None:
            return None
        schedules[index] = schedule
        storage.update_server(server_id, {"schedules": schedules})
        register_job(server_id, schedule)
    return _annotate(schedule)


def delete_schedule(server_id: str, schedule_id: str) -> bool:
    with _write_lock:
        schedules = _schedules_of(server_id)
        kept = [s for s in schedules if s.get("id") != schedule_id]
        if len(kept) == len(schedules):
            return False
        storage.update_server(server_id, {"schedules": kept})
        remove_job(schedule_id)
    _last_runs.pop(schedule_id, None)
    return True


def _annotate(schedule: Dict[str, Any]) -> Dict[str, Any]:
    return {
        **schedule,
        "nextRunTime": _next_run(schedule.get("id")),
        "lastRun": _last_runs.get(schedule.get("id")),
    }


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------


def _job_id(schedule_id: str) -> str:
    return f"cmd-{schedule_id}"


def _scheduler_ready() -> bool:
    # Module attributes, not imported names: tests reload the scheduler module.
    return sched_mod._initialised and not sched_mod._is_disabled()


def register_job(server_id: str, schedule: Dict[str, Any]) -> None:
    """Add/replace the job for ``schedule``, or remove it when disabled. Never raises."""
    if not _scheduler_ready():
        return
    if not schedule.get("enabled"):
        remove_job(schedule["id"])
        return
    try:
        sched_mod.scheduler.add_job(
            id=_job_id(schedule["id"]),
            func="backend.schedules.service:run_schedule",
            args=[server_id, schedule["id"]],
            trigger=_build_trigger(schedule),
            replace_existing=True,
            misfire_grace_time=60,
        )
    except Exception:
        logger.exception("Failed to register schedule %s", schedule.get("id"))


def remove_job(schedule_id: Optional[str]) -> None:
    if not _scheduler_ready() or not schedule_id:
        return
    try:
        sched_mod.scheduler.remove_job(_job_id(schedule_id))
    except Exception:
        pass  # JobLookupError: nothing registered (e.g. disabled schedule)


def register_all_jobs() -> None:
    """Register every enabled schedule. Called once at boot after the scheduler starts."""
    if not _scheduler_ready():
        return
    try:
        servers = storage.get_all_servers()
    except Exception as exc:
        logger.warning("Could not load servers to register schedules: %s", exc)
        return
    for server in servers:
        for schedule in server.get("schedules") or []:
            # Stored schedules come from validate(), but servers.json can be
            # hand-edited: skip a bad entry rather than fail the panel's boot.
            clean, error = validate(schedule)
            schedule_id = schedule.get("id") if isinstance(schedule, dict) else None
            if error or not schedule_id:
                logger.warning(
                    "Skipping invalid schedule %s on %s: %s",
                    schedule_id, server.get("id"), error or "missing id",
                )
                continue
            register_job(server.get("id"), {"id": schedule_id, **clean})


def _next_run(schedule_id: str) -> Optional[str]:
    if not _scheduler_ready():
        return None
    job = sched_mod.scheduler.get_job(_job_id(schedule_id))
    if job is None or job.next_run_time is None:
        return None
    return job.next_run_time.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def run_schedule(server_id: str, schedule_id: str) -> None:
    """APScheduler entry point, also used by "run now". Never raises.

    ponytail: delays sleep on one of the scheduler's shared pool threads (10 by
    default) for the whole run; give runs their own thread if many long
    schedules appear. Overlapping fires of one schedule are skipped by
    APScheduler's max_instances=1.
    """
    try:
        schedule = get_schedule(server_id, schedule_id)
        if schedule is None:
            return  # deleted since the job fired
        status, message = _run_steps(server_id, schedule["steps"])
    except Exception as exc:
        logger.exception("Schedule %s on %s failed", schedule_id, server_id)
        status, message = "error", str(exc)
    logger.info("Schedule %s on %s: %s (%s)", schedule_id, server_id, status, message)
    _last_runs[schedule_id] = {"at": iso_z_now(), "status": status, "message": message}


def _run_steps(server_id: str, steps: List[Dict[str, Any]]) -> Tuple[str, str]:
    registry = get_server_process_registry()
    running = registry.get_status(server_id).get("status") == "running"
    if not running and steps[0]["action"] != "start":
        return "skipped", "Server is not running"

    for i, step in enumerate(steps, 1):
        time.sleep(step["delaySeconds"])
        if step["action"] == "command":
            result = registry.send_command(server_id, step["command"])
            if not result.get("success"):
                return "error", f"Step {i}: {result.get('message') or 'command failed'}"
            continue
        # Same lock the start/restart routes and backups take, so a scheduled
        # restart can't interleave with a manual one or a backup shutdown.
        with get_server_lock(server_id):
            server = storage.get_server(server_id)
            if server is None:
                return "error", "Server no longer exists"
            ok, message = _power(registry, server, step["action"])
        if not ok:
            return "error", f"Step {i}: {message}"
    return "ok", f"Ran {len(steps)} step(s)"


def _power(registry, server: Dict[str, Any], action: str) -> Tuple[bool, str]:
    """Start/stop/restart, mirroring the routes' guards and status writes."""
    server_id = server["id"]
    if server.get("status") in ("pending", "installing"):
        return False, f"Server is {server['status']}"

    if action == "stop":
        result = registry.stop_server(server_id)
        status = result.get("status", "stopped")
        storage.update_server_status(server_id, status)
        return status == "stopped", result.get("message") or "Server did not stop"

    if action == "start":
        compat = resolve_required_java(str(server.get("version") or ""))
        required = compat.required_java if compat.enforceable else None
        result = registry.start_server(
            server, required_java_major=None if skip_java_enforcement() else required
        )
    else:
        result = registry.restart_server(server)["start"]  # raises if the stop half fails

    # A stop still draining: leave the persisted 'stopping' alone, as the start route does.
    if result.get("stopping"):
        return False, result.get("message") or "Server is still stopping"
    status = result.get("status")
    if status:
        storage.update_server_status(server_id, status)
    return status == "running", result.get("message") or f"Server did not {action}"
