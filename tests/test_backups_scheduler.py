"""Scheduler integration (``backend.backups.scheduler``).

Pins:
- ``register_all_jobs`` is idempotent across re-init (``replace_existing=True``).
- Delete removes the job from APScheduler's store.
- ``FABRICATOR_DISABLE_SCHEDULER=1`` shorts out init entirely (used by
  the rest of the pytest suite to avoid background timers leaking
  between tests).

The tests start the scheduler in paused mode so the trigger callbacks
never fire — we only assert on the job-store state.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest
from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask

# We import the package-level scheduler module under a paused replacement
# scheduler so we never spawn real backups during tests.


@pytest.fixture
def paused_scheduler(tmp_servers_root, monkeypatch):
    """Reload the scheduler module, swap in a paused BackgroundScheduler.

    The flask-apscheduler ``APScheduler`` wrapper delegates everything
    to an underlying APScheduler instance; substituting a paused one
    means ``add_job`` etc. all work but no callbacks fire.
    """
    monkeypatch.setenv("BACKUPS_DIR", str(tmp_servers_root / "backups-sched"))
    monkeypatch.delenv("FABRICATOR_DISABLE_SCHEDULER", raising=False)

    import importlib
    import backend.backups.storage as storage
    import backend.backups.scheduler as scheduler_mod
    importlib.reload(storage)
    importlib.reload(scheduler_mod)
    scheduler_mod.reset_for_tests()
    storage.reset_for_tests()

    paused = BackgroundScheduler(timezone="UTC")
    paused.start(paused=True)
    # flask-apscheduler reads ``_scheduler`` after ``init_app``; we swap
    # it in directly so ``init_scheduler`` is a no-op for the underlying
    # APScheduler instance but still walks our register-all-jobs path.
    scheduler_mod.scheduler._scheduler = paused
    scheduler_mod._initialised = True

    app = Flask(__name__)
    yield {
        "storage": storage,
        "scheduler": scheduler_mod,
        "app": app,
        "paused": paused,
    }
    try:
        paused.shutdown(wait=False)
    except Exception:
        pass
    scheduler_mod.reset_for_tests()
    storage.reset_for_tests()


def test_register_job_creates_job(paused_scheduler):
    storage = paused_scheduler["storage"]
    sched = paused_scheduler["scheduler"]

    cfg = storage.create_config(
        "srv_sc",
        {
            "name": "Daily",
            "storagePath": "/tmp/store",
            "schedule": {
                "enabled": True,
                "frequencyHours": 24,
                "timeOfDay": "03:30",
            },
        },
    )

    job_id = sched.register_job(cfg)
    assert job_id == f"backup-{cfg['id']}"
    job = sched.scheduler.get_job(job_id)
    assert job is not None
    info = sched.get_job_info(cfg["id"])
    assert info["job_id"] == job_id


def test_register_all_jobs_is_idempotent(paused_scheduler):
    """Second call to register_all_jobs must not raise + must keep one job."""
    storage = paused_scheduler["storage"]
    sched = paused_scheduler["scheduler"]

    cfg = storage.create_config(
        "srv_sc2",
        {
            "name": "X",
            "storagePath": "/tmp/x",
            "schedule": {
                "enabled": True,
                "frequencyHours": 6,
                "timeOfDay": "02:00",
            },
        },
    )

    sched.register_all_jobs()
    sched.register_all_jobs()

    jobs = sched.scheduler.get_jobs()
    backup_jobs = [j for j in jobs if j.id == f"backup-{cfg['id']}"]
    assert len(backup_jobs) == 1


def test_disabled_schedule_removes_job(paused_scheduler):
    storage = paused_scheduler["storage"]
    sched = paused_scheduler["scheduler"]

    cfg = storage.create_config(
        "srv_sc3",
        {
            "name": "Y",
            "storagePath": "/tmp/y",
            "schedule": {
                "enabled": True,
                "frequencyHours": 24,
                "timeOfDay": "04:00",
            },
        },
    )

    sched.register_job(cfg)
    assert sched.scheduler.get_job(f"backup-{cfg['id']}") is not None

    cfg["schedule"]["enabled"] = False
    sched.register_job(cfg)
    assert sched.scheduler.get_job(f"backup-{cfg['id']}") is None


def test_remove_job_removes_from_store(paused_scheduler):
    storage = paused_scheduler["storage"]
    sched = paused_scheduler["scheduler"]

    cfg = storage.create_config(
        "srv_sc4",
        {
            "name": "Z",
            "storagePath": "/tmp/z",
            "schedule": {
                "enabled": True,
                "frequencyHours": 24,
                "timeOfDay": "05:15",
            },
        },
    )
    sched.register_job(cfg)
    assert sched.remove_job(cfg["id"]) is True
    assert sched.scheduler.get_job(f"backup-{cfg['id']}") is None
    # Second remove is a no-op (returns False rather than raising).
    assert sched.remove_job(cfg["id"]) is False


def test_disable_env_var_short_circuits_init(tmp_servers_root, monkeypatch):
    """With FABRICATOR_DISABLE_SCHEDULER=1, init_scheduler is a full no-op."""
    monkeypatch.setenv("FABRICATOR_DISABLE_SCHEDULER", "1")
    monkeypatch.setenv("BACKUPS_DIR", str(tmp_servers_root / "backups-dis"))

    import importlib
    import backend.backups.scheduler as scheduler_mod
    importlib.reload(scheduler_mod)
    scheduler_mod.reset_for_tests()

    app = Flask(__name__)
    scheduler_mod.init_scheduler(app)

    # Internal flag never flips because init bails on the env-gate.
    assert scheduler_mod._initialised is False
    # register_job / remove_job are inert without init.
    assert scheduler_mod.register_job({"id": "bkc_x"}) is None
    assert scheduler_mod.remove_job("bkc_x") is False


# ---------------------------------------------------------------------------
# Trigger timezone handling. A schedule's ``timezone`` (the user's browser
# zone) is fed to both triggers so ``timeOfDay`` fires at the USER's wall-clock
# time, not the server's. With no zone stored (pre-fix configs) both triggers
# fall back to the host zone via a naive anchor — the old behaviour, unchanged.
# ---------------------------------------------------------------------------


def test_interval_anchor_uses_today_when_slot_still_ahead():
    from datetime import time as dtime
    import backend.backups.scheduler as scheduler_mod

    now = datetime(2026, 7, 2, 1, 0)          # 01:00 — 03:30 slot still ahead today
    anchor = scheduler_mod._interval_anchor(dtime(3, 30), 6, now)
    assert anchor == datetime(2026, 7, 2, 3, 30)
    assert anchor.tzinfo == now.tzinfo        # stays in `now`'s frame, not forced to UTC


def test_interval_anchor_rolls_forward_when_slot_passed():
    from datetime import time as dtime
    import backend.backups.scheduler as scheduler_mod

    now = datetime(2026, 7, 2, 5, 0)          # 05:00 — 03:30 already passed today
    anchor = scheduler_mod._interval_anchor(dtime(3, 30), 6, now)
    assert anchor == datetime(2026, 7, 2, 9, 30)   # rolled forward by frequency (6h)


def test_subdaily_trigger_without_timezone_falls_back_to_naive_local(monkeypatch):
    """With no stored zone, _build_trigger feeds a naive (host-local) `now` into
    the anchor — the same frame the host-default CronTrigger uses. This is the
    backward-compat path for configs created before the timezone fix."""
    from apscheduler.triggers.interval import IntervalTrigger
    import backend.backups.scheduler as scheduler_mod

    captured = {}
    real_anchor = scheduler_mod._interval_anchor

    def spy(time_of_day, frequency_hours, now):
        captured["now"] = now
        return real_anchor(time_of_day, frequency_hours, now)

    monkeypatch.setattr(scheduler_mod, "_interval_anchor", spy)
    trig = scheduler_mod._build_trigger({"frequencyHours": 6, "timeOfDay": "03:30"})

    assert isinstance(trig, IntervalTrigger)
    assert captured["now"].tzinfo is None, \
        "with no zone the anchor must stay naive (host-local), not become UTC-aware"


def test_resolve_timezone_reads_stored_zone_and_falls_back():
    """_resolve_timezone: real zone → ZoneInfo; missing/blank/garbage → None."""
    from zoneinfo import ZoneInfo
    import backend.backups.scheduler as scheduler_mod

    assert scheduler_mod._resolve_timezone(
        {"timezone": "America/New_York"}
    ) == ZoneInfo("America/New_York")
    # Absent, blank, and unknown zones all fall back to the host default (None).
    assert scheduler_mod._resolve_timezone({}) is None
    assert scheduler_mod._resolve_timezone({"timezone": ""}) is None
    assert scheduler_mod._resolve_timezone({"timezone": "   "}) is None
    assert scheduler_mod._resolve_timezone({"timezone": "Not/AZone"}) is None


def test_daily_trigger_uses_stored_timezone():
    """Daily CronTrigger must carry the schedule's zone so 03:00 means 03:00
    THERE, not 03:00 on the (UTC) host."""
    from apscheduler.triggers.cron import CronTrigger
    import backend.backups.scheduler as scheduler_mod

    trig = scheduler_mod._build_trigger(
        {"frequencyHours": 24, "timeOfDay": "03:00", "timezone": "America/New_York"}
    )
    assert isinstance(trig, CronTrigger)
    assert str(trig.timezone) == "America/New_York"


def test_subdaily_trigger_uses_stored_timezone(monkeypatch):
    """Sub-daily IntervalTrigger must carry the zone AND anchor in it (aware now),
    keeping daily and sub-daily schedules with the same timeOfDay aligned."""
    from apscheduler.triggers.interval import IntervalTrigger
    import backend.backups.scheduler as scheduler_mod

    captured = {}
    real_anchor = scheduler_mod._interval_anchor

    def spy(time_of_day, frequency_hours, now):
        captured["now"] = now
        return real_anchor(time_of_day, frequency_hours, now)

    monkeypatch.setattr(scheduler_mod, "_interval_anchor", spy)
    trig = scheduler_mod._build_trigger(
        {"frequencyHours": 6, "timeOfDay": "03:30", "timezone": "America/New_York"}
    )

    assert isinstance(trig, IntervalTrigger)
    assert str(trig.timezone) == "America/New_York"
    assert captured["now"].tzinfo is not None
    assert str(captured["now"].tzinfo) == "America/New_York"


def test_daily_trigger_fires_at_local_wall_clock_across_the_utc_offset():
    """End-to-end: the whole point of the fix. A New York 03:00 daily schedule
    must fire at 03:00 New York time — proven by converting the next fire back
    to that zone — regardless of the UTC host. DST-agnostic (checks wall clock,
    not a hard-coded UTC hour)."""
    from datetime import datetime
    from zoneinfo import ZoneInfo
    import backend.backups.scheduler as scheduler_mod

    ny = ZoneInfo("America/New_York")
    trig = scheduler_mod._build_trigger(
        {"frequencyHours": 24, "timeOfDay": "03:00", "timezone": "America/New_York"}
    )
    now = datetime(2026, 7, 16, 12, 0, tzinfo=ZoneInfo("UTC"))  # noon UTC
    next_fire = trig.get_next_fire_time(None, now)

    assert next_fire is not None
    local = next_fire.astimezone(ny)
    assert (local.hour, local.minute) == (3, 0)
    # And it is NOT 03:00 on the UTC host — that was exactly the bug.
    assert next_fire.astimezone(ZoneInfo("UTC")).hour != 3
