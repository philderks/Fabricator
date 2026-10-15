"""Scheduled commands (``backend.schedules``).

Pins:
- Validation rejects multi-line commands, unknown actions, out-of-range
  delays, numeric cron weekdays (APScheduler 3 counts Monday as 0) and cron
  expressions restricting both day fields (APScheduler ANDs them).
- A daily trigger fires on the chosen weekdays in the schedule's zone.
- The runner executes steps in order, skips a stopped server, stops at the
  first failing step, and never starts a server that is still installing.
- Jobs follow the ``enabled`` flag; CRUD round-trips over HTTP.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from backend.schedules import service


SERVER_ID = "srv_sched"


def _body(**overrides):
    body = {
        "name": "Restart",
        "enabled": True,
        "timezone": "Europe/Amsterdam",
        "trigger": {"type": "daily", "time": "04:00", "days": []},
        "steps": [{"action": "command", "command": "say hi", "delaySeconds": 0}],
    }
    body.update(overrides)
    return body


def _seed_server(tmp_root: Path, schedules=None, status="running"):
    (tmp_root / "servers.json").write_text(
        json.dumps([{
            "id": SERVER_ID, "name": "X", "version": "1.20.1", "loader": "fabric",
            "port": 25565, "installPath": SERVER_ID, "status": status,
            "schedules": schedules or [],
        }]),
        encoding="utf-8",
    )


@pytest.mark.parametrize("overrides", [
    {"steps": [{"action": "command", "command": "say hi\nop me", "delaySeconds": 0}]},
    {"steps": [{"action": "explode", "delaySeconds": 0}]},
    {"steps": [{"action": "stop", "delaySeconds": 3601}]},
    {"steps": [{"action": "stop", "delaySeconds": True}]},
    {"steps": []},
    {"trigger": {"type": "cron", "expression": "0 4 * * 0"}},
    {"trigger": {"type": "cron", "expression": "0 4 * * 1-5"}},
    {"trigger": {"type": "cron", "expression": "0 4 * * */2"}},
    {"trigger": {"type": "cron", "expression": "0 4 1 * mon"}},
    {"trigger": {"type": "cron", "expression": "99 4 * * *"}},
    {"trigger": {"type": "interval", "minutes": 0}},
    {"trigger": {"type": "daily", "time": "4pm", "days": []}},
    {"timezone": "Mars/Olympus"},
])
def test_validate_rejects(overrides):
    clean, error = service.validate(_body(**overrides))
    assert clean is None and error


@pytest.mark.parametrize("expression", [
    "0 4 * * sun", "*/15 * * * *", "0 4 * * mon-fri", "0 */6 * * *", "0 4 1 * *",
])
def test_validate_accepts_cron(expression):
    clean, error = service.validate(_body(trigger={"type": "cron", "expression": expression}))
    assert error is None, error


def test_daily_trigger_fires_on_chosen_days_in_local_time():
    clean, _ = service.validate(
        _body(trigger={"type": "daily", "time": "04:00", "days": ["sun", "sat"]})
    )
    assert clean["trigger"]["days"] == ["sat", "sun"]
    tz = ZoneInfo("Europe/Amsterdam")
    wednesday_noon = datetime(2026, 10, 14, 12, 0, tzinfo=tz)
    fire = service._build_trigger(clean).get_next_fire_time(None, wednesday_noon)
    assert fire == datetime(2026, 10, 17, 4, 0, tzinfo=tz)


class _FakeRegistry:
    def __init__(self, running=True, fail=False):
        self.running, self.fail, self.calls = running, fail, []

    def get_status(self, server_id):
        return {"status": "running" if self.running else "stopped"}

    def send_command(self, server_id, command):
        self.calls.append(command)
        return {"success": not self.fail, "message": "boom"}

    def start_server(self, server, required_java_major=None):
        self.calls.append("<start>")
        return {"status": "running"}

    def restart_server(self, server):
        self.calls.append("<restart>")
        return {"stop": {"status": "stopped"}, "start": {"status": "running"}}


@pytest.fixture
def run_with(tmp_servers_root, monkeypatch):
    """Seed one schedule with ``steps`` and run it against a fake registry."""
    def run(steps, status="running", **registry_kwargs):
        clean, error = service.validate(_body(steps=steps))
        assert error is None, error
        _seed_server(Path(tmp_servers_root), [{"id": "sch_1", **clean}], status)
        fake = _FakeRegistry(**registry_kwargs)
        monkeypatch.setattr(service, "get_server_process_registry", lambda: fake)
        monkeypatch.setattr(
            service, "time", SimpleNamespace(sleep=lambda s: fake.calls.append(f"<sleep {s}>"))
        )
        service.run_schedule(SERVER_ID, "sch_1")
        return fake.calls, service._last_runs.pop("sch_1")
    return run


def test_runner_executes_steps_in_order(run_with):
    calls, last = run_with([
        {"action": "command", "command": "say bye", "delaySeconds": 0},
        {"action": "restart", "delaySeconds": 5},
    ])
    assert calls == ["<sleep 0>", "say bye", "<sleep 5>", "<restart>"]
    assert last["status"] == "ok"


def test_runner_skips_stopped_server(run_with):
    calls, last = run_with(
        [{"action": "command", "command": "say hi", "delaySeconds": 0}], running=False
    )
    assert calls == []
    assert last["status"] == "skipped"


def test_runner_stops_at_failed_command(run_with):
    calls, last = run_with([
        {"action": "command", "command": "a", "delaySeconds": 0},
        {"action": "command", "command": "b", "delaySeconds": 0},
    ], fail=True)
    assert "b" not in calls
    assert last["status"] == "error"


def test_runner_starts_a_stopped_server_and_persists_status(run_with, tmp_servers_root):
    calls, last = run_with(
        [{"action": "start", "delaySeconds": 0}], status="stopped", running=False
    )
    assert calls == ["<sleep 0>", "<start>"]
    assert last["status"] == "ok"
    saved = json.loads((Path(tmp_servers_root) / "servers.json").read_text())
    assert saved[0]["status"] == "running"


def test_runner_never_starts_an_installing_server(run_with):
    calls, last = run_with(
        [{"action": "start", "delaySeconds": 0}], status="installing", running=False
    )
    assert "<start>" not in calls
    assert last["status"] == "error"


@pytest.fixture
def paused(monkeypatch):
    """A started-but-paused scheduler swapped in: jobs register, none fire."""
    from apscheduler.schedulers.background import BackgroundScheduler

    # The module service holds, not a fresh import: test_app_factory.py purges
    # backend.* from sys.modules, so the two can differ.
    sched_mod = service.sched_mod
    monkeypatch.delenv("FABRICATOR_DISABLE_SCHEDULER", raising=False)
    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.start(paused=True)
    monkeypatch.setattr(sched_mod.scheduler, "_scheduler", scheduler)
    monkeypatch.setattr(sched_mod, "_initialised", True)
    yield scheduler
    scheduler.shutdown(wait=False)


def test_register_job_follows_enabled_flag(paused):
    schedule = {"id": "sch_job", **service.validate(_body())[0]}
    service.register_job(SERVER_ID, schedule)
    assert paused.get_job("cmd-sch_job") is not None
    assert service._next_run("sch_job").endswith("Z")

    service.register_job(SERVER_ID, {**schedule, "enabled": False})
    assert paused.get_job("cmd-sch_job") is None


def test_boot_skips_invalid_schedules(paused, tmp_servers_root):
    good = {"id": "sch_good", **service.validate(_body())[0]}
    _seed_server(Path(tmp_servers_root), [
        {"enabled": True},  # no id
        {"id": "sch_bad", **_body(steps=[{"action": "command", "command": "a\nb"}])},
        "not a schedule",
        good,
    ])
    service.register_all_jobs()
    assert [job.id for job in paused.get_jobs()] == ["cmd-sch_good"]


@pytest.fixture
def no_scheduler(monkeypatch):
    monkeypatch.setenv("FABRICATOR_DISABLE_SCHEDULER", "1")


def test_crud_round_trip(no_scheduler, client, tmp_servers_root):
    _seed_server(Path(tmp_servers_root))
    base = f"/api/servers/{SERVER_ID}/schedules"

    assert client.get(base).get_json() == []
    assert client.post(base, json=_body(steps=[])).status_code == 400

    created = client.post(base, json=_body())
    assert created.status_code == 201
    schedule_id = created.get_json()["id"]

    updated = client.put(f"{base}/{schedule_id}", json=_body(name="Renamed", enabled=False))
    assert updated.status_code == 200
    assert [s["name"] for s in client.get(base).get_json()] == ["Renamed"]
    assert client.put(f"{base}/sch_missing", json=_body()).status_code == 404

    assert client.delete(f"{base}/{schedule_id}").status_code == 200
    assert client.delete(f"{base}/{schedule_id}").status_code == 404
    assert client.get("/api/servers/srv_nope/schedules").status_code == 404
    assert client.post(f"{base}/sch_missing/run").status_code == 404


def test_server_create_drops_schedules(no_scheduler, client, tmp_servers_root):
    response = client.post("/api/servers", json={
        "name": "New", "version": "1.20.1", "loader": "fabric", "port": 25570,
        "installPath": "srv_new", "schedules": [{"id": "sch_x", "steps": "junk"}],
    })
    assert response.status_code in (200, 201), response.get_json()
    saved = json.loads((Path(tmp_servers_root) / "servers.json").read_text())
    assert all("schedules" not in server for server in saved)
