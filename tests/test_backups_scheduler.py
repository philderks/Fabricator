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
