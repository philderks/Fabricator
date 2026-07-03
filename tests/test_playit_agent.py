"""Tests for backend.playit.agent — the lifecycle state machine.

Coverage focus, per plan:
  * cancel-during-claim (the security-critical race)
  * sensitive-logging on the REAL Popen-exchange path (not run_cli)
  * restart-race (slow reader of old generation must not corrupt new state)
  * stop-race
  * reset semantics (stop FIRST, then unlink)
  * windows-guard
  * missing-binary error surfacing
  * happy-path daemon connect
"""
from __future__ import annotations

import importlib
import logging
import subprocess
import threading
import time
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest


SECRET_MARKER = "FAKE_SECRET_AAA_BBB_DO_NOT_LOG_ME"
CLAIM_CODE    = "fakecode123"
CLAIM_URL     = "https://playit.gg/claim/fakecode123"


# ---------------------------------------------------------------------------
# Fixture: reset module state + redirect runtime dir for every test
# ---------------------------------------------------------------------------

@pytest.fixture
def agent(tmp_path, monkeypatch):
    """Yield a fresh import of backend.playit.agent against a temp runtime dir."""
    monkeypatch.setenv("PLAYIT_RUNTIME_DIR", str(tmp_path))
    monkeypatch.delenv("PLAYIT_BINARY_VERIFIED", raising=False)

    from backend.playit import agent as agent_mod
    importlib.reload(agent_mod)

    # Sanity: state must be clean.
    with agent_mod._lock:
        agent_mod._proc          = None
        agent_mod._exchange_proc = None
        agent_mod._status        = "stopped"
        agent_mod._tunnels       = []
        agent_mod._tunnels_known = False
        agent_mod._claim_url     = None
        agent_mod._error_reason  = None
        agent_mod._gen           = 0

    yield agent_mod

    # Teardown: drain lingering lifecycle / rundata threads before the next
    # test starts. These are daemon threads that resolve the runtime dir via
    # the PLAYIT_RUNTIME_DIR env var at call time — if one outlives its test
    # it would read the NEXT test's tmp_path and could clear that test's PID
    # file mid-assertion. stop() bumps the generation; the gen-checked threads
    # exit within one 0.5s sleep chunk, so we wait for the playit-named
    # threads to die (bounded) before releasing the fixture.
    try:
        agent_mod.stop()
    except Exception:
        pass

    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        alive = [t for t in threading.enumerate()
                 if t.name.startswith(("playit-lifecycle-", "playit-rundata-"))
                 and t.is_alive()]
        if not alive:
            break
        time.sleep(0.05)


def _make_completed(stdout: str = "", rc: int = 0) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=rc, stdout=stdout, stderr="")


def _wait_for(condition, timeout: float = 2.0, interval: float = 0.02) -> bool:
    """Poll until `condition()` returns truthy or timeout expires."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(interval)
    return False


# ---------------------------------------------------------------------------
# Missing-binary error surfacing
# ---------------------------------------------------------------------------

def test_start_without_daemon_binary_sets_error(agent):
    """start() must surface a structured error, not raise."""
    with patch("backend.playit.binary.find_daemon", return_value=None), \
         patch("backend.playit.binary.find_cli", return_value="/fake/playit-cli"):
        agent.start()
        status = agent.get_status()
    assert status["status"] == "error"
    assert "daemon binary not found" in status["error_reason"]


def test_start_without_cli_binary_sets_error(agent):
    with patch("backend.playit.binary.find_daemon", return_value="/fake/playit"), \
         patch("backend.playit.binary.find_cli", return_value=None):
        agent.start()
        status = agent.get_status()
    assert status["status"] == "error"
    assert "playit-cli binary not found" in status["error_reason"]


def test_redundant_start_does_not_reap_own_running_daemon(agent):
    """A redundant start() while our daemon is alive must NOT reap it — the PID
    file points at our own healthy daemon, so reaping would kill the live
    tunnel and defeat the 'already running' fast-return."""
    reaped = {"called": False}
    agent._reap_orphan_daemon = lambda: reaped.__setitem__("called", True)

    alive = MagicMock(spec=subprocess.Popen)
    alive.poll.return_value = None       # daemon is alive
    alive.pid = 4321
    with agent._lock:
        agent._proc = alive
        agent._status = "running"

    agent.start()

    assert reaped["called"] is False, "start() reaped our own live daemon"
    assert agent._proc is alive          # daemon left untouched
    assert agent.get_status()["status"] == "running"


def test_start_without_own_daemon_still_reaps_orphan(agent):
    """When we do NOT own a live daemon, start() must still reap a leftover
    orphan from a previous run (guard against over-suppressing the reap)."""
    reaped = {"called": False}
    agent._reap_orphan_daemon = lambda: reaped.__setitem__("called", True)

    # _proc is None from the fixture. Missing binaries make start() bail right
    # after the reap.
    with patch("backend.playit.binary.find_daemon", return_value=None), \
         patch("backend.playit.binary.find_cli", return_value=None):
        agent.start()

    assert reaped["called"] is True


# ---------------------------------------------------------------------------
# Happy-path claim + daemon connect
# ---------------------------------------------------------------------------

class _BlockingStdout:
    """Iterator that yields `lines` then blocks on an Event (simulates a
    still-alive daemon whose stdout is open but quiet)."""

    def __init__(self, lines, hold: threading.Event):
        self._lines = list(lines)
        self._hold  = hold

    def __iter__(self):
        return self

    def __next__(self):
        if self._lines:
            return self._lines.pop(0)
        # Real daemon would just have stdout quiet — block until the test releases us.
        self._hold.wait(timeout=10.0)
        raise StopIteration


def _make_fake_daemon_proc(stdout_lines, hold: Optional[threading.Event] = None, pid: int = 99999):
    """Build a Popen-like mock whose stdout yields `stdout_lines` then blocks.

    If `hold` is provided, the reader thread will park there until the test
    sets the event — modelling a long-running daemon. Without it, stdout EOFs
    immediately and the reader runs proc.wait(), which is what stop()-tests want.
    """
    proc = MagicMock(spec=subprocess.Popen)
    if hold is not None:
        proc.stdout = _BlockingStdout(stdout_lines, hold)
    else:
        proc.stdout = iter(stdout_lines)
    proc.pid = pid                       # not in spec by default; lifecycle writes PID file
    proc.poll.return_value = None
    proc.returncode = 0
    proc.wait = MagicMock(return_value=0)
    proc.terminate = MagicMock()
    proc.kill = MagicMock()
    return proc


def test_happy_path_claim_to_daemon_spawn(agent, tmp_path):
    """Full bootstrap: generate → url → exchange → daemon spawn → starting.

    At the checkpoint (PID file just written) the status is still "starting":
    the rundata poller hasn't run yet (initial backoff), and even once it does
    the fake secret isn't valid hex so _read_secret_for_api returns None and no
    rundata call is made. The test asserts the bootstrap reached daemon-spawn,
    not the steady state.
    """
    fake_exchange = MagicMock(spec=subprocess.Popen)
    fake_exchange.communicate.return_value = (SECRET_MARKER, "")
    fake_exchange.returncode = 0
    fake_exchange.poll.return_value = None

    daemon_hold  = threading.Event()
    fake_daemon  = _make_fake_daemon_proc([], hold=daemon_hold)

    def fake_popen(cmd, **kwargs):
        if "claim" in cmd:
            return fake_exchange
        return fake_daemon

    def fake_run_cli(*args, **kwargs):
        if args[0] == "claim" and args[1] == "generate":
            return _make_completed(stdout=CLAIM_CODE + "\n")
        if args[0] == "claim" and args[1] == "url":
            return _make_completed(stdout=CLAIM_URL + "\n")
        raise AssertionError(f"unexpected run_cli call: {args}")

    with patch("backend.playit.binary.find_daemon", return_value="/fake/playit"), \
         patch("backend.playit.binary.find_cli",    return_value="/fake/playit-cli"), \
         patch("backend.playit.binary.run_cli",     side_effect=fake_run_cli), \
         patch("subprocess.Popen",                  side_effect=fake_popen):
        try:
            agent.start()

            # The PID file is only written AFTER the daemon Popen, which is
            # itself AFTER the secret atomic-write. So waiting on the PID file
            # appearance is a precise checkpoint: claim → secret → daemon.
            pid_file = tmp_path / "playit.pid"
            assert _wait_for(lambda: pid_file.exists(), timeout=3.0), \
                f"daemon never spawned; status={agent.get_status()}"
            assert agent.get_status()["status"] == "starting"

            # Secret persisted with 0600 — atomic write completed.
            secret_file = tmp_path / "playit.toml"
            assert secret_file.exists()
            assert secret_file.read_text() == SECRET_MARKER
            mode = secret_file.stat().st_mode & 0o777
            assert mode == 0o600, f"secret file mode is {oct(mode)}, expected 0o600"

            # PID file content reflects the daemon Popen.
            assert int(pid_file.read_text().strip()) == fake_daemon.pid
        finally:
            daemon_hold.set()


def test_existing_secret_skips_claim_bootstrap(agent, tmp_path):
    """If the secret file already exists, daemon launches directly (no claim)."""
    secret_file = tmp_path / "playit.toml"
    secret_file.write_text("preexisting")
    secret_file.chmod(0o600)

    daemon_hold = threading.Event()
    fake_daemon = _make_fake_daemon_proc([], hold=daemon_hold)

    run_cli_calls = []

    def fake_run_cli(*args, **kwargs):
        run_cli_calls.append(args)
        return _make_completed()

    with patch("backend.playit.binary.find_daemon", return_value="/fake/playit"), \
         patch("backend.playit.binary.find_cli",    return_value="/fake/playit-cli"), \
         patch("backend.playit.binary.run_cli",     side_effect=fake_run_cli), \
         patch("subprocess.Popen",                  return_value=fake_daemon):
        try:
            agent.start()
            assert _wait_for(lambda: agent.get_status()["status"] == "starting", timeout=3.0)
            # No `claim generate` etc. — bootstrap was skipped because secret already existed.
            assert run_cli_calls == [], f"unexpected CLI calls: {run_cli_calls}"
        finally:
            daemon_hold.set()


# ---------------------------------------------------------------------------
# Secret-write failure (e.g. unwritable runtime dir) must surface an error,
# not hang at "claiming" with the daemon never starting.
# ---------------------------------------------------------------------------

def test_claim_secret_write_failure_surfaces_error(agent, tmp_path):
    """If the secret can't be persisted, surface a clear error instead of
    leaving the UI stuck on 'claiming'. Regression: a PermissionError from an
    unwritable runtime dir used to kill the lifecycle thread silently."""
    fake_exchange = MagicMock(spec=subprocess.Popen)
    fake_exchange.communicate.return_value = (SECRET_MARKER, "")
    fake_exchange.returncode = 0
    fake_exchange.poll.return_value = None

    daemon_spawned = [0]

    def fake_popen(cmd, **kwargs):
        if "claim" in cmd:
            return fake_exchange
        daemon_spawned[0] += 1
        return _make_fake_daemon_proc([])

    def fake_run_cli(*args, **kwargs):
        if args[1] == "generate":
            return _make_completed(stdout=CLAIM_CODE + "\n")
        if args[1] == "url":
            return _make_completed(stdout=CLAIM_URL + "\n")
        raise AssertionError(f"unexpected run_cli: {args}")

    def boom(*a, **k):
        raise PermissionError(13, "Permission denied")

    with patch("backend.playit.binary.find_daemon", return_value="/fake/playit"), \
         patch("backend.playit.binary.find_cli",    return_value="/fake/playit-cli"), \
         patch("backend.playit.binary.run_cli",     side_effect=fake_run_cli), \
         patch("subprocess.Popen",                  side_effect=fake_popen), \
         patch.object(agent, "_atomic_write_secret", side_effect=boom):
        agent.start()
        assert _wait_for(lambda: agent.get_status()["status"] == "error", timeout=3.0), \
            f"never surfaced error; got {agent.get_status()}"

    status = agent.get_status()
    assert "could not save the playit secret" in (status["error_reason"] or "")
    assert "PLAYIT_RUNTIME_DIR" in (status["error_reason"] or "")
    assert daemon_spawned[0] == 0, "daemon must not spawn when the secret wasn't saved"
    assert not (tmp_path / "playit.toml").exists()


# ---------------------------------------------------------------------------
# CANCEL-DURING-CLAIM — security-critical: tunnel must NOT come up after stop()
# ---------------------------------------------------------------------------

def test_cancel_during_claim_does_not_persist_secret(agent, tmp_path):
    """User clicks OFF while the exchange subprocess is still blocked.

    Expected: stop() bumps _gen → exchange thread sees mismatch → secret
    NOT written, daemon NOT spawned, status stays 'stopped'.
    """
    exchange_blocked = threading.Event()
    exchange_released = threading.Event()
    daemon_spawn_count = [0]

    fake_exchange = MagicMock(spec=subprocess.Popen)
    fake_exchange.poll.return_value = None

    def blocking_communicate(timeout=None):
        # Hold until the test releases us (simulating the user not having
        # clicked the claim URL yet).
        exchange_blocked.set()
        exchange_released.wait(timeout=5.0)
        return (SECRET_MARKER, "")
    fake_exchange.communicate = MagicMock(side_effect=blocking_communicate)
    fake_exchange.returncode = 0
    fake_exchange.terminate = MagicMock()
    fake_exchange.kill = MagicMock()
    fake_exchange.wait = MagicMock(return_value=0)

    def fake_popen(cmd, **kwargs):
        if "claim" in cmd:
            return fake_exchange
        # Daemon Popen — should NEVER be hit in this test.
        daemon_spawn_count[0] += 1
        return _make_fake_daemon_proc([])

    def fake_run_cli(*args, **kwargs):
        if args[1] == "generate":
            return _make_completed(stdout=CLAIM_CODE + "\n")
        if args[1] == "url":
            return _make_completed(stdout=CLAIM_URL + "\n")
        raise AssertionError(f"unexpected run_cli: {args}")

    with patch("backend.playit.binary.find_daemon", return_value="/fake/playit"), \
         patch("backend.playit.binary.find_cli",    return_value="/fake/playit-cli"), \
         patch("backend.playit.binary.run_cli",     side_effect=fake_run_cli), \
         patch("subprocess.Popen",                  side_effect=fake_popen):
        agent.start()
        # Wait until the exchange subprocess is alive AND blocked on user
        # approval. Status stays "claiming" for the whole user-action window
        # so the URL remains surfaced — see backend/playit/agent.py docstring.
        def in_claim_wait():
            with agent._lock:
                return (
                    agent._status == "claiming"
                    and agent._exchange_proc is fake_exchange
                    and exchange_blocked.is_set()
                )
        assert _wait_for(in_claim_wait, timeout=3.0), \
            f"never entered claim-wait; status={agent.get_status()}"

        # User clicks OFF.
        agent.stop()
        # Release the blocked exchange — it now "returns" the secret, but it's too late.
        exchange_released.set()

        # Give the lifecycle thread time to wake up and see the gen mismatch.
        time.sleep(0.2)

    final = agent.get_status()
    assert final["status"] == "stopped", f"status was {final}"
    assert final["tunnels"] == []
    assert final["claim_url"] is None

    # Secret file MUST NOT exist — user said no.
    secret_file = tmp_path / "playit.toml"
    assert not secret_file.exists(), \
        "SECURITY: secret was persisted after user-requested cancel"

    # Daemon must never have been spawned.
    assert daemon_spawn_count[0] == 0, \
        "SECURITY: daemon was launched after user-requested cancel"

    # stop() must have terminated the live exchange subprocess.
    assert fake_exchange.terminate.called


# ---------------------------------------------------------------------------
# SENSITIVE-LOGGING — secret must not appear in any log record
# ---------------------------------------------------------------------------

def test_secret_marker_not_logged_during_happy_path(agent, tmp_path, caplog):
    """The exchange-Popen path is secret-bearing. Marker must never leak."""
    fake_exchange = MagicMock(spec=subprocess.Popen)
    fake_exchange.communicate.return_value = (SECRET_MARKER, "")
    fake_exchange.returncode = 0
    fake_exchange.poll.return_value = None

    daemon_hold = threading.Event()
    fake_daemon = _make_fake_daemon_proc([], hold=daemon_hold)

    def fake_popen(cmd, **kwargs):
        if "claim" in cmd:
            return fake_exchange
        return fake_daemon

    def fake_run_cli(*args, **kwargs):
        if args[1] == "generate":
            return _make_completed(stdout=CLAIM_CODE + "\n")
        if args[1] == "url":
            return _make_completed(stdout=CLAIM_URL + "\n")
        raise AssertionError(f"unexpected run_cli: {args}")

    caplog.set_level(logging.DEBUG, logger="backend.playit")

    with patch("backend.playit.binary.find_daemon", return_value="/fake/playit"), \
         patch("backend.playit.binary.find_cli",    return_value="/fake/playit-cli"), \
         patch("backend.playit.binary.run_cli",     side_effect=fake_run_cli), \
         patch("subprocess.Popen",                  side_effect=fake_popen):
        try:
            agent.start()
            # Wait until the secret-bearing exchange path has completed
            # (status reaches "starting" after secret is written and daemon spawned).
            assert _wait_for(lambda: agent.get_status()["status"] == "starting", timeout=3.0)

            # CRITICAL: scan every captured log record AND the rendered text.
            assert SECRET_MARKER not in caplog.text, \
                f"SECRET LEAK in caplog.text"
            for rec in caplog.records:
                msg = rec.getMessage()
                assert SECRET_MARKER not in msg, \
                    f"SECRET LEAK in record: {rec.levelname} {rec.name}: {msg!r}"
                assert SECRET_MARKER not in str(rec.args), \
                    f"SECRET LEAK in record.args: {rec.args!r}"
        finally:
            daemon_hold.set()


def test_secret_marker_not_logged_on_timeout(agent, caplog):
    """Even when communicate() times out we must not leak the (un-bound) marker."""
    fake_exchange = MagicMock(spec=subprocess.Popen)
    fake_exchange.communicate.side_effect = subprocess.TimeoutExpired(
        cmd="claim exchange", timeout=605, output=SECRET_MARKER, stderr=""
    )
    fake_exchange.returncode = -9
    fake_exchange.poll.return_value = None
    fake_exchange.terminate = MagicMock()
    fake_exchange.kill = MagicMock()
    fake_exchange.wait = MagicMock(return_value=0)

    def fake_popen(cmd, **kwargs):
        if "claim" in cmd:
            return fake_exchange
        raise AssertionError("daemon must not be spawned after timeout")

    def fake_run_cli(*args, **kwargs):
        if args[1] == "generate":
            return _make_completed(stdout=CLAIM_CODE + "\n")
        if args[1] == "url":
            return _make_completed(stdout=CLAIM_URL + "\n")
        raise AssertionError(f"unexpected run_cli: {args}")

    caplog.set_level(logging.DEBUG, logger="backend.playit")

    with patch("backend.playit.binary.find_daemon", return_value="/fake/playit"), \
         patch("backend.playit.binary.find_cli",    return_value="/fake/playit-cli"), \
         patch("backend.playit.binary.run_cli",     side_effect=fake_run_cli), \
         patch("subprocess.Popen",                  side_effect=fake_popen):
        agent.start()
        assert _wait_for(lambda: agent.get_status()["status"] == "error", timeout=3.0), \
            f"never reached error; got {agent.get_status()}"

    final = agent.get_status()
    assert "claim timed out" in (final["error_reason"] or "")
    assert SECRET_MARKER not in caplog.text, \
        "SECRET LEAK via TimeoutExpired output"
    assert SECRET_MARKER not in (final["error_reason"] or ""), \
        "SECRET LEAK in error_reason"


# ---------------------------------------------------------------------------
# Generation-token race tests
# ---------------------------------------------------------------------------

def test_restart_race_old_reader_does_not_overwrite_new_state(agent):
    """An old reader thread finishing late must not flip status to error."""
    # Manually drive the reader function with a stale generation.
    with agent._lock:
        agent._gen = 5
        agent._status = "running"
        agent._tunnels = [{"local_port": 25565, "address": "alpha.gl.joinmc.link",
                           "disabled_reason": None, "name": "Test",
                           "tunnel_type": "minecraft-java"}]
        agent._tunnels_known = True

    # Fake an old proc that has already exited non-zero.
    old_proc = MagicMock(spec=subprocess.Popen)
    old_proc.stdout = iter([])
    old_proc.wait.return_value = -15
    old_proc.returncode = -15

    # my_gen=4 < current _gen=5 → reader must silently exit.
    agent._read_daemon_stdout(old_proc, my_gen=4)

    status = agent.get_status()
    assert status["status"] == "running", \
        f"stale reader corrupted state: {status}"
    assert status["tunnels"][0]["address"] == "alpha.gl.joinmc.link"
    assert status["tunnels_known"] is True


def test_stop_then_late_reader_does_not_set_error(agent):
    """stop() bumps gen; a slow reader of the now-dead proc must noop."""
    with agent._lock:
        agent._gen = 1
        agent._status = "running"

    agent.stop()  # bumps _gen to 2, sets status=stopped

    # Old reader from gen=1 wakes up.
    old_proc = MagicMock(spec=subprocess.Popen)
    old_proc.stdout = iter([])
    old_proc.wait.return_value = -15
    old_proc.returncode = -15
    agent._read_daemon_stdout(old_proc, my_gen=1)

    assert agent.get_status()["status"] == "stopped"


# ---------------------------------------------------------------------------
# Self-exit of the daemon: poller must not resurrect it, and must be retired
# ---------------------------------------------------------------------------

def _rundata_with_tunnel(local_port: str = "25565",
                         address: str = "alpha.gl.joinmc.link") -> dict:
    """Build a minimal rundata body that reports one live server-side tunnel."""
    return {"data": {"tunnels": [{
        "agent_config": {"fields": [{"name": "local_port", "value": local_port}]},
        "display_address": address,
        "name": "Test",
        "tunnel_type": "minecraft-java",
    }]}}


def test_rundata_does_not_resurrect_exited_daemon(agent):
    """A daemon that died on its own leaves _status='error' (non-inline tail
    reason). A late rundata cycle still sees server-side tunnels — it must NOT
    flip the state back to 'running', because the local daemon is gone."""
    dead = MagicMock(spec=subprocess.Popen)
    dead.poll.return_value = 1                     # process has exited
    with agent._lock:
        agent._proc = dead
        agent._status = "error"
        agent._error_reason = "playitd exited with code 1"
        agent._apply_rundata_to_state(_rundata_with_tunnel())

    status = agent.get_status()
    assert status["status"] == "error", f"dead daemon resurrected: {status}"
    assert status["error_reason"] == "playitd exited with code 1"


def test_rundata_sets_running_when_daemon_alive(agent):
    """Regression guard for the resurrection fix: while the daemon is alive,
    rundata must still drive 'starting' → 'running' and populate tunnels."""
    alive = MagicMock(spec=subprocess.Popen)
    alive.poll.return_value = None                # still running
    with agent._lock:
        agent._proc = alive
        agent._status = "starting"
        agent._apply_rundata_to_state(_rundata_with_tunnel())

    status = agent.get_status()
    assert status["status"] == "running"
    assert status["tunnels"][0]["address"] == "alpha.gl.joinmc.link"
    assert status["tunnels_known"] is True


def test_run_daemon_retires_generation_when_daemon_exits(agent, tmp_path):
    """When the daemon exits on its own, _run_daemon must advance _gen so the
    rundata poller spawned for that generation exits (no thread leak, and no
    chance to resurrect the dead daemon on a later cycle)."""
    fake = MagicMock(spec=subprocess.Popen)
    fake.stdout = iter([])                         # EOF at once → daemon exited
    fake.pid = 4242
    fake.poll.return_value = 1
    fake.returncode = 1
    fake.wait = MagicMock(return_value=1)

    with agent._lock:
        agent._gen = 7

    started_gens = []
    with patch("subprocess.Popen", return_value=fake), \
         patch.object(agent, "_start_rundata_poller",
                      side_effect=lambda g: started_gens.append(g)):
        agent._run_daemon(my_gen=7, daemon_bin="/fake/playit",
                          secret=tmp_path / "secret.toml")

    assert started_gens == [7], "poller should have been started for gen 7"
    assert agent._gen == 8, "generation must advance so the stale poller exits"
    assert agent.get_status()["status"] == "error"   # rc=1 → terminal error


def test_poller_retires_generation_when_daemon_exited(agent, monkeypatch):
    """Fallback path: if the daemon exits but the stdout reader is still blocked
    (a child holds the pipe open, so _run_daemon never bumps _gen), the poller
    itself must notice the dead process, refuse the stale 'live' rundata, and
    retire its generation so it stops polling."""
    dead = MagicMock(spec=subprocess.Popen)
    dead.poll.return_value = 137                      # exited (OOM-killed)
    with agent._lock:
        agent._gen = 3
        agent._proc = dead
        agent._status = "running"

    # rundata still reports a live tunnel (playit.gg lags a local exit); the
    # poller must NOT trust it. Make the cycle instant.
    monkeypatch.setattr(agent, "_read_secret_for_api", lambda: "a" * 64)
    monkeypatch.setattr(agent, "_call_rundata", lambda secret: _rundata_with_tunnel())
    monkeypatch.setattr(agent, "_RUNDATA_INITIAL_BACKOFF", 0)

    t = threading.Thread(target=agent._rundata_poller, args=(3,),
                         name="playit-rundata-3", daemon=True)
    t.start()
    t.join(timeout=3.0)

    assert not t.is_alive(), "poller failed to retire and kept polling a dead daemon"
    assert agent._gen == 4, "poller must advance _gen to retire the generation"
    status = agent.get_status()
    assert status["status"] == "error", "non-zero exit must map to 'error'"
    assert "137" in (status["error_reason"] or ""), \
        "error_reason must reflect the daemon's exit code"


def test_poller_clean_exit_reports_stopped_not_error(agent, monkeypatch):
    """A clean daemon self-exit (rc 0) detected by the poller fallback must be
    reported as 'stopped', not a spurious 'error' — mirroring the reader path's
    rc-aware classification rather than blindly forcing 'error'."""
    dead = MagicMock(spec=subprocess.Popen)
    dead.poll.return_value = 0                         # clean exit
    with agent._lock:
        agent._gen = 5
        agent._proc = dead
        agent._status = "running"

    monkeypatch.setattr(agent, "_read_secret_for_api", lambda: "a" * 64)
    monkeypatch.setattr(agent, "_call_rundata", lambda secret: _rundata_with_tunnel())
    monkeypatch.setattr(agent, "_RUNDATA_INITIAL_BACKOFF", 0)

    t = threading.Thread(target=agent._rundata_poller, args=(5,),
                         name="playit-rundata-5", daemon=True)
    t.start()
    t.join(timeout=3.0)

    assert not t.is_alive()
    assert agent._gen == 6, "poller must retire the generation on clean exit too"
    assert agent.get_status()["status"] == "stopped", "clean exit must not be 'error'"


def test_poller_transient_error_does_not_run_exited_daemon(agent, monkeypatch):
    """A transient rundata failure (body=None) must not flip an already-exited
    daemon from 'starting' to 'running' via the transient window branch."""
    dead = MagicMock(spec=subprocess.Popen)
    dead.poll.return_value = 1
    with agent._lock:
        agent._gen = 2
        agent._proc = dead
        agent._status = "starting"

    monkeypatch.setattr(agent, "_read_secret_for_api", lambda: "a" * 64)
    monkeypatch.setattr(agent, "_call_rundata", lambda secret: None)   # transient
    monkeypatch.setattr(agent, "_RUNDATA_INITIAL_BACKOFF", 0)

    t = threading.Thread(target=agent._rundata_poller, args=(2,),
                         name="playit-rundata-2", daemon=True)
    t.start()
    t.join(timeout=3.0)

    assert not t.is_alive()
    assert agent.get_status()["status"] != "running", \
        "exited daemon was labeled 'running' via the transient branch"
    assert agent._gen == 3


# ---------------------------------------------------------------------------
# Reset semantics (Feedback F)
# ---------------------------------------------------------------------------

def test_reset_stops_before_unlinking_secret(agent, tmp_path):
    """reset() must call stop() BEFORE deleting the secret file."""
    secret_file = tmp_path / "playit.toml"
    secret_file.write_text("preexisting-secret")
    secret_file.chmod(0o600)

    call_order = []

    real_stop   = agent.stop
    real_unlink = Path.unlink

    def tracking_stop():
        call_order.append("stop")
        real_stop()
    def tracking_unlink(self, *args, **kwargs):
        if self == secret_file:
            call_order.append("unlink")
        return real_unlink(self, *args, **kwargs)

    with patch.object(agent, "stop", side_effect=tracking_stop), \
         patch.object(Path, "unlink", tracking_unlink):
        agent.reset()

    assert call_order == ["stop", "unlink"], \
        f"reset() called in wrong order: {call_order}"
    assert not secret_file.exists()
    assert agent.get_status()["status"] == "stopped"


def test_reset_with_no_secret_file_is_idempotent(agent):
    """reset() must not crash if the secret was never written."""
    agent.reset()
    assert agent.get_status()["status"] == "stopped"


# ---------------------------------------------------------------------------
# Persistent enabled-state (folded in from colleague's commit, adapted to
# the backend/playit/ layout — survives a service restart)
# ---------------------------------------------------------------------------

def test_is_enabled_defaults_false_without_state_or_env(agent, monkeypatch):
    monkeypatch.delenv("PLAYIT_ENABLED", raising=False)
    assert agent.is_enabled() is False


def test_is_enabled_falls_back_to_env_var(agent, monkeypatch):
    monkeypatch.setenv("PLAYIT_ENABLED", "true")
    assert agent.is_enabled() is True
    monkeypatch.setenv("PLAYIT_ENABLED", "false")
    assert agent.is_enabled() is False


def test_set_enabled_persists_and_overrides_env(agent, monkeypatch, tmp_path):
    """The state file is authoritative over the env var."""
    monkeypatch.setenv("PLAYIT_ENABLED", "false")
    agent.set_enabled(True)
    assert (tmp_path / "playit.enabled").read_text().strip() == "true"
    assert agent.is_enabled() is True            # file wins over env=false

    agent.set_enabled(False)
    assert agent.is_enabled() is False           # file wins over... still false


def test_stop_persists_disabled_so_restart_stays_down(agent, monkeypatch):
    """A deliberately stopped tunnel must not auto-start after restart, even
    when PLAYIT_ENABLED=true in the environment."""
    monkeypatch.setenv("PLAYIT_ENABLED", "true")
    agent.stop()
    assert agent.is_enabled() is False, \
        "stop() must persist disabled-state to override an enabled env var"


# ---------------------------------------------------------------------------
# Platform guard
# ---------------------------------------------------------------------------

def test_windows_guard_returns_unsupported(agent):
    """On Windows, get_status() returns 'unsupported' and start/stop no-op."""
    with patch("backend.utils.platform.is_windows", return_value=True):
        status = agent.get_status()
        assert status["status"] == "unsupported"
        agent.start()
        agent.stop()
        # No state mutation happened — get_status still says unsupported.
        assert agent.get_status()["status"] == "unsupported"


# ---------------------------------------------------------------------------
# binary_verified passthrough
# ---------------------------------------------------------------------------

def test_binary_verified_reflects_env(agent, monkeypatch):
    monkeypatch.setenv("PLAYIT_BINARY_VERIFIED", "true")
    assert agent.get_status()["binary_verified"] is True

    monkeypatch.setenv("PLAYIT_BINARY_VERIFIED", "false")
    assert agent.get_status()["binary_verified"] is False

    monkeypatch.delenv("PLAYIT_BINARY_VERIFIED", raising=False)
    assert agent.get_status()["binary_verified"] is False


# ---------------------------------------------------------------------------
# runtime_dir resolution (env → writable default → per-user fallback) + the
# writability guard used at startup
# ---------------------------------------------------------------------------

def test_runtime_dir_writable_true_for_creatable_dir(monkeypatch, tmp_path):
    """A not-yet-existing dir under a writable ancestor counts as writable."""
    from backend.playit import binary as b
    monkeypatch.setenv("PLAYIT_RUNTIME_DIR", str(tmp_path / "sub" / "playit"))
    assert b.runtime_dir_writable() is True


def test_runtime_dir_writable_false_when_no_writable_ancestor(monkeypatch, tmp_path):
    """No writable ancestor → not usable (the dev /var/lib/fabricator case)."""
    from backend.playit import binary as b
    monkeypatch.setenv("PLAYIT_RUNTIME_DIR", str(tmp_path / "x" / "y"))
    monkeypatch.setattr(b.os, "access", lambda *a, **k: False)
    assert b.runtime_dir_writable() is False


def test_runtime_dir_env_var_takes_precedence(monkeypatch, tmp_path):
    """PLAYIT_RUNTIME_DIR wins over both the default and the fallback."""
    from backend.playit import binary as b
    monkeypatch.setenv("PLAYIT_RUNTIME_DIR", str(tmp_path / "explicit"))
    assert b.runtime_dir() == tmp_path / "explicit"


def test_runtime_dir_uses_default_when_writable(monkeypatch):
    """No env + writable default → the systemd /var/lib path (production)."""
    from backend.playit import binary as b
    monkeypatch.delenv("PLAYIT_RUNTIME_DIR", raising=False)
    monkeypatch.setattr(b, "_writable_or_creatable", lambda p: True)
    assert str(b.runtime_dir()) == "/var/lib/fabricator/playit"


def test_runtime_dir_falls_back_to_appdata_when_default_unwritable(monkeypatch, tmp_path):
    """No env + unwritable default (dev) → per-user ~/.fabricator/playit."""
    from backend.playit import binary as b
    monkeypatch.delenv("PLAYIT_RUNTIME_DIR", raising=False)
    monkeypatch.setattr(b, "_writable_or_creatable", lambda p: False)
    monkeypatch.setattr(b.platform_utils, "appdata_dir", lambda: tmp_path / ".fabricator")
    assert b.runtime_dir() == tmp_path / ".fabricator" / "playit"


# ---------------------------------------------------------------------------
# Exchange-stdout parser — playit-cli v1.0.5 emits a reminder loop, the
# secret only appears as the trailing line on success. Verified against the
# live v1.0.5 binary on 2026-05-29 (see plan F).
# ---------------------------------------------------------------------------

def test_extract_exchange_secret_realistic_output(agent):
    """Realistic v1.0.5 exchange stdout: reminder block + secret token."""
    raw = (
        "Open this link to finish setting up playit:\n"
        "https://playit.gg/claim/abc123\n"
        "Open this link to finish setting up playit:\n"
        "https://playit.gg/claim/abc123\n"
        "Open this link to finish setting up playit:\n"
        "https://playit.gg/claim/abc123\n"
        "FAKE_SECRET_TOKEN_XYZ\n"
    )
    assert agent._extract_exchange_secret(raw) == "FAKE_SECRET_TOKEN_XYZ"


def test_extract_exchange_secret_only_reminder_returns_none(agent):
    """If exchange exited before the secret was produced, refuse to write."""
    raw = (
        "Open this link to finish setting up playit:\n"
        "https://playit.gg/claim/abc123\n"
    )
    assert agent._extract_exchange_secret(raw) is None


def test_extract_exchange_secret_empty_returns_none(agent):
    assert agent._extract_exchange_secret("") is None
    assert agent._extract_exchange_secret("   \n\n   \n") is None


# ---------------------------------------------------------------------------
# Daemon failure-pattern detection (Target 1 — real cause in error_reason)
# ---------------------------------------------------------------------------

# Realistic v1.0.5 daemon log line, verified live on 2026-05-29.
_AGENT_DISABLED_LINE = (
    "\x1b[2m2026-05-29T11:59:34.010000Z\x1b[0m \x1b[33m WARN\x1b[0m "
    "\x1b[2mplayitd::daemon\x1b[0m\x1b[2m:\x1b[0m agent disabled because the "
    "account is over the agent limit error=ApiFail(\"\\\"AgentDisabledOverLimit\\\"\")\n"
)


def test_daemon_agent_disabled_flips_to_error_with_actionable_reason(agent, tmp_path):
    """When the daemon emits AgentDisabledOverLimit, surface a user-actionable
    reason inline instead of waiting for proc exit (the daemon retries forever)."""
    # Pre-existing secret so we skip claim and go straight to daemon spawn.
    (tmp_path / "playit.toml").write_text("preexisting")
    (tmp_path / "playit.toml").chmod(0o600)

    daemon_hold = threading.Event()
    fake_daemon = _make_fake_daemon_proc([_AGENT_DISABLED_LINE], hold=daemon_hold)

    with patch("backend.playit.binary.find_daemon", return_value="/fake/playit"), \
         patch("backend.playit.binary.find_cli",    return_value="/fake/playit-cli"), \
         patch("subprocess.Popen",                  return_value=fake_daemon):
        try:
            agent.start()
            assert _wait_for(lambda: agent.get_status()["status"] == "error", timeout=3.0), \
                f"never reached error; got {agent.get_status()}"

            status = agent.get_status()
            assert "agent limit" in (status["error_reason"] or "").lower() \
                or "different account" in (status["error_reason"] or "").lower(), \
                f"error_reason should mention the actual cause; got {status['error_reason']!r}"
            # Must NOT be the useless "exited with code N" fallback.
            assert "exited with code" not in (status["error_reason"] or "")
        finally:
            daemon_hold.set()


def test_strip_ansi_removes_tracing_escapes(agent):
    line = "\x1b[2m2026-05-29\x1b[0m \x1b[33m WARN\x1b[0m message"
    assert agent._strip_ansi(line) == "2026-05-29  WARN message"


def test_match_daemon_error_recognises_known_substrings(agent):
    assert agent._match_daemon_error("error=ApiFail(\"AgentDisabledOverLimit\")") is not None
    assert agent._match_daemon_error("WARN agent disabled because") is not None
    assert agent._match_daemon_error("invalid secret rejected") is not None
    assert agent._match_daemon_error("normal info line") is None


# ---------------------------------------------------------------------------
# rundata poller — primary source for address + tunnel state
# ---------------------------------------------------------------------------
# Verified against the live v1.0.5 API on 2026-05-29. Response shape:
#   { "status": "success",
#     "data": {
#       "tunnels": [
#         { "display_address": "true-mint.gl.joinmc.link",
#           "disabled_reason": null, ... }
#       ], "pending": [], "notices": [],
#       "permissions": {...} } }


def _rundata_active_response(address="alpha.gl.joinmc.link", local_port="25565"):
    return {
        "status": "success",
        "data": {
            "agent_id": "agent-uuid",
            "tunnels": [
                {
                    "id": "tun-uuid",
                    "name": "Test",
                    "display_address": address,
                    "tunnel_type": "minecraft-java",
                    "port_type": "tcp",
                    "port_count": 1,
                    "agent_config": {"fields": [
                        {"name": "local_ip", "value": "127.0.0.1"},
                        {"name": "local_port", "value": local_port},
                    ]},
                    "disabled_reason": None,
                }
            ],
            "pending": [],
            "notices": [],
            "permissions": {"is_self_managed": True, "has_premium": False, "account_status": "verified"},
        },
    }


def _rundata_empty_response():
    return {
        "status": "success",
        "data": {
            "agent_id": "agent-uuid",
            "tunnels": [],
            "pending": [],
            "notices": [],
            "permissions": {"is_self_managed": True, "has_premium": False, "account_status": "verified"},
        },
    }


def _rundata_disabled_response(reason="legal-review", local_port="25565"):
    return {
        "status": "success",
        "data": {
            "agent_id": "agent-uuid",
            "tunnels": [
                {
                    "id": "tun-uuid",
                    "name": "Test",
                    "display_address": None,
                    "tunnel_type": "minecraft-java",
                    "agent_config": {"fields": [
                        {"name": "local_port", "value": local_port},
                    ]},
                    "disabled_reason": reason,
                }
            ],
            "pending": [],
            "notices": [],
            "permissions": {"is_self_managed": True, "has_premium": False, "account_status": "verified"},
        },
    }


def _spawn_daemon_with_rundata(agent, tmp_path, rundata_result, daemon_hold, monkeypatch):
    """Boot the lifecycle past daemon spawn with a controllable _call_rundata."""
    monkeypatch.setattr(agent, "_RUNDATA_INITIAL_BACKOFF", 0.05)
    monkeypatch.setattr(agent, "_RUNDATA_INTERVAL_SECONDS", 0.1)

    (tmp_path / "playit.toml").write_text("d" * 64)  # 64-hex-char fake secret
    (tmp_path / "playit.toml").chmod(0o600)

    fake_daemon = _make_fake_daemon_proc([], hold=daemon_hold)
    call_count = [0]

    def fake_call(_secret):
        call_count[0] += 1
        return rundata_result(call_count[0]) if callable(rundata_result) else rundata_result

    return fake_daemon, call_count, [
        patch("backend.playit.binary.find_daemon", return_value="/fake/playit"),
        patch("backend.playit.binary.find_cli",    return_value="/fake/playit-cli"),
        patch("subprocess.Popen",                  return_value=fake_daemon),
        patch.object(agent, "_call_rundata",        side_effect=fake_call),
    ]


def test_rundata_active_tunnel_populates_tunnels(agent, tmp_path, monkeypatch):
    """rundata with an active tunnel → status=running, tunnel parsed into _tunnels
    with an int local_port and its address."""
    daemon_hold = threading.Event()
    fake_daemon, _, patches = _spawn_daemon_with_rundata(
        agent, tmp_path, _rundata_active_response("beta.gl.joinmc.link", "25566"), daemon_hold, monkeypatch,
    )

    with patches[0], patches[1], patches[2], patches[3]:
        try:
            agent.start()
            assert _wait_for(lambda: agent.get_status()["tunnels_known"], timeout=2.0), \
                f"never got authoritative tunnels; got {agent.get_status()}"
            status = agent.get_status()
            assert status["status"] == "running"
            assert len(status["tunnels"]) == 1
            t = status["tunnels"][0]
            assert t["local_port"] == 25566 and isinstance(t["local_port"], int)
            assert t["address"] == "beta.gl.joinmc.link"
            assert t["disabled_reason"] is None
        finally:
            daemon_hold.set()


def test_rundata_empty_tunnels_running_and_known(agent, tmp_path, monkeypatch):
    """Empty tunnels[] → status=running, _tunnels==[], tunnels_known True. The
    'go create a tunnel' hint is now per-server (frontend), NOT a global state."""
    daemon_hold = threading.Event()
    fake_daemon, _, patches = _spawn_daemon_with_rundata(
        agent, tmp_path, _rundata_empty_response(), daemon_hold, monkeypatch,
    )

    with patches[0], patches[1], patches[2], patches[3]:
        try:
            agent.start()
            assert _wait_for(lambda: agent.get_status()["tunnels_known"], timeout=2.0), \
                f"never got authoritative empty list; got {agent.get_status()}"
            status = agent.get_status()
            assert status["status"] == "running"
            assert status["tunnels"] == []
            assert status["error_reason"] is None
        finally:
            daemon_hold.set()


def test_rundata_disabled_tunnel_stays_running_reason_preserved(agent, tmp_path, monkeypatch):
    """A disabled tunnel is NOT a global error — status stays running and the
    disabled_reason rides per-tunnel for the frontend to surface for that server."""
    daemon_hold = threading.Event()
    fake_daemon, _, patches = _spawn_daemon_with_rundata(
        agent, tmp_path, _rundata_disabled_response("policy-violation"), daemon_hold, monkeypatch,
    )

    with patches[0], patches[1], patches[2], patches[3]:
        try:
            agent.start()
            assert _wait_for(lambda: agent.get_status()["tunnels_known"], timeout=2.0), \
                f"never got tunnels; got {agent.get_status()}"
            status = agent.get_status()
            assert status["status"] == "running"        # NOT global error
            assert status["error_reason"] is None
            assert status["tunnels"][0]["disabled_reason"] == "policy-violation"
        finally:
            daemon_hold.set()


def test_rundata_two_tunnels_both_parsed(agent, tmp_path, monkeypatch):
    """Two active tunnels → both parsed with int local_ports + their addresses."""
    resp = _rundata_active_response("first.gl.joinmc.link", "25565")
    resp["data"]["tunnels"].append({
        "id": "tun-uuid-2",
        "name": "Test2",
        "display_address": "second.gl.joinmc.link",
        "tunnel_type": "minecraft-java",
        "port_type": "tcp",
        "port_count": 1,
        "agent_config": {"fields": [{"name": "local_port", "value": "25566"}]},
        "disabled_reason": None,
    })

    daemon_hold = threading.Event()
    fake_daemon, _, patches = _spawn_daemon_with_rundata(
        agent, tmp_path, resp, daemon_hold, monkeypatch,
    )
    with patches[0], patches[1], patches[2], patches[3]:
        try:
            agent.start()
            assert _wait_for(lambda: len(agent.get_status()["tunnels"]) == 2, timeout=2.0), \
                f"never parsed both tunnels; got {agent.get_status()}"
            status = agent.get_status()
            assert status["status"] == "running"
            by_port = {t["local_port"]: t for t in status["tunnels"]}
            assert set(by_port) == {25565, 25566}
            assert by_port[25565]["address"] == "first.gl.joinmc.link"
            assert by_port[25566]["address"] == "second.gl.joinmc.link"
        finally:
            daemon_hold.set()


def test_rundata_unparseable_local_port_skipped(agent, tmp_path, monkeypatch):
    """A tunnel whose local_port can't be parsed is skipped, others survive,
    and the poll still counts as authoritative (tunnels_known True)."""
    resp = _rundata_active_response("ok.gl.joinmc.link", "25565")
    resp["data"]["tunnels"].append({
        "id": "tun-bad",
        "name": "Bad",
        "display_address": "bad.gl.joinmc.link",
        "tunnel_type": "minecraft-java",
        "agent_config": {"fields": [{"name": "local_port", "value": "not-a-number"}]},
        "disabled_reason": None,
    })

    daemon_hold = threading.Event()
    fake_daemon, _, patches = _spawn_daemon_with_rundata(
        agent, tmp_path, resp, daemon_hold, monkeypatch,
    )
    with patches[0], patches[1], patches[2], patches[3]:
        try:
            agent.start()
            assert _wait_for(lambda: agent.get_status()["tunnels_known"], timeout=2.0), \
                f"never authoritative; got {agent.get_status()}"
            status = agent.get_status()
            assert status["status"] == "running"        # no crash on bad port
            assert [t["local_port"] for t in status["tunnels"]] == [25565]
        finally:
            daemon_hold.set()


def test_rundata_network_failure_keeps_neutral_running(agent, tmp_path, monkeypatch):
    """API unreachable → status=running (neutral), NOT error, and tunnels stay
    UNKNOWN (tunnels_known False) so the UI shows 'can't confirm', not 'create one'."""
    daemon_hold = threading.Event()
    fake_daemon, _, patches = _spawn_daemon_with_rundata(
        agent, tmp_path, None,  # transient failure
        daemon_hold, monkeypatch,
    )

    with patches[0], patches[1], patches[2], patches[3]:
        try:
            agent.start()
            assert _wait_for(lambda: agent.get_status()["status"] == "running", timeout=2.0), \
                f"never reached running; got {agent.get_status()}"
            status = agent.get_status()
            assert status["status"] != "error"          # not red UI
            assert status["error_reason"] is None
            assert status["tunnels"] == []
            assert status["tunnels_known"] is False      # the "unknown" case
        finally:
            daemon_hold.set()


def test_stdout_AgentDisabled_beats_rundata_response(agent, tmp_path, monkeypatch):
    """If the daemon's stdout already surfaced AgentDisabledOverLimit, a slower
    rundata response must NOT stamp over that more-specific error."""
    daemon_hold = threading.Event()

    monkeypatch.setattr(agent, "_RUNDATA_INITIAL_BACKOFF", 0.05)
    monkeypatch.setattr(agent, "_RUNDATA_INTERVAL_SECONDS", 0.2)

    (tmp_path / "playit.toml").write_text("d" * 64)
    (tmp_path / "playit.toml").chmod(0o600)

    fake_daemon = _make_fake_daemon_proc([_AGENT_DISABLED_LINE], hold=daemon_hold)

    with patch("backend.playit.binary.find_daemon", return_value="/fake/playit"), \
         patch("backend.playit.binary.find_cli",    return_value="/fake/playit-cli"), \
         patch("subprocess.Popen",                  return_value=fake_daemon), \
         patch.object(agent, "_call_rundata", return_value=_rundata_empty_response()):
        try:
            agent.start()
            # First the stdout AgentDisabled pattern should win.
            assert _wait_for(
                lambda: "agent limit" in (agent.get_status()["error_reason"] or "").lower(),
                timeout=2.0,
            )
            # Wait an extra interval to ensure rundata DOES NOT overwrite.
            time.sleep(0.4)
            assert agent.get_status()["status"] == "error"
            assert "agent limit" in (agent.get_status()["error_reason"] or "").lower(), \
                "rundata stomped over the stdout AgentDisabled signal"
        finally:
            daemon_hold.set()


def test_rundata_secret_never_logged(agent, tmp_path, monkeypatch, caplog):
    """The secret must not appear in any log record emitted by the rundata path,
    even when the API call errors out (HTTPError/URLError paths)."""
    secret = "f" * 64
    (tmp_path / "playit.toml").write_text(secret)
    (tmp_path / "playit.toml").chmod(0o600)

    import urllib.error
    fake_http_err = urllib.error.HTTPError(
        url="https://api.playit.gg/v1/agents/rundata",
        code=401,
        msg="Unauthorized",
        hdrs=None,
        fp=None,
    )
    caplog.set_level(logging.DEBUG, logger="backend.playit")

    with patch("urllib.request.urlopen", side_effect=fake_http_err):
        result = agent._call_rundata(secret)

    assert result is agent._RUNDATA_UNAUTHORIZED   # 401 → distinct sentinel, not None
    assert secret not in caplog.text, "SECRET LEAK via rundata error path"
    for rec in caplog.records:
        assert secret not in rec.getMessage()
        assert secret not in str(rec.args)


def test_rundata_persistent_401_surfaces_invalid_agent_error(agent, tmp_path, monkeypatch):
    """A persistent 401 (agent deleted/revoked on playit.gg) must surface an
    actionable error, not sit on a misleading 'running/active'."""
    monkeypatch.setattr(agent, "_RUNDATA_AUTH_FAIL_LIMIT", 2)
    daemon_hold = threading.Event()
    fake_daemon, _, patches = _spawn_daemon_with_rundata(
        agent, tmp_path, agent._RUNDATA_UNAUTHORIZED, daemon_hold, monkeypatch,
    )
    with patches[0], patches[1], patches[2], patches[3]:
        try:
            agent.start()
            assert _wait_for(lambda: agent.get_status()["status"] == "error", timeout=2.0), \
                f"never surfaced auth error; got {agent.get_status()}"
            status = agent.get_status()
            assert "401" in (status["error_reason"] or "")
            assert status["tunnels_known"] is False
        finally:
            daemon_hold.set()


# ---------------------------------------------------------------------------
# PID file + orphan reaping (Target 1b)
# ---------------------------------------------------------------------------

def test_pid_file_written_on_daemon_spawn(agent, tmp_path):
    (tmp_path / "playit.toml").write_text("preexisting")
    (tmp_path / "playit.toml").chmod(0o600)

    daemon_hold = threading.Event()
    fake_daemon = _make_fake_daemon_proc([], hold=daemon_hold, pid=12345)

    with patch("backend.playit.binary.find_daemon", return_value="/fake/playit"), \
         patch("backend.playit.binary.find_cli",    return_value="/fake/playit-cli"), \
         patch("subprocess.Popen",                  return_value=fake_daemon):
        try:
            agent.start()
            assert _wait_for(lambda: (tmp_path / "playit.pid").exists(), timeout=2.0)
            assert int((tmp_path / "playit.pid").read_text().strip()) == 12345
        finally:
            daemon_hold.set()


def test_start_reaps_orphan_from_previous_run(agent, tmp_path):
    """If a PID file points at a live daemon we don't own, terminate it
    before spawning a new one — prevents two daemons fighting over the socket."""
    # Stale PID file from "previous run"
    (tmp_path / "playit.pid").write_text("88888")

    reaped = []

    def fake_is_alive(pid):
        return pid == 88888 and 88888 not in reaped

    def fake_reap(pid):
        reaped.append(pid)

    (tmp_path / "playit.toml").write_text("preexisting")
    (tmp_path / "playit.toml").chmod(0o600)

    daemon_hold = threading.Event()
    fake_daemon = _make_fake_daemon_proc([], hold=daemon_hold, pid=99999)

    with patch("backend.playit.binary.find_daemon", return_value="/fake/playit"), \
         patch("backend.playit.binary.find_cli",    return_value="/fake/playit-cli"), \
         patch("subprocess.Popen",                  return_value=fake_daemon), \
         patch.object(agent, "_is_pid_alive",       side_effect=fake_is_alive), \
         patch.object(agent, "_reap_pid",           side_effect=fake_reap):
        try:
            agent.start()
            _wait_for(lambda: agent.get_status()["status"] == "starting", timeout=2.0)
            assert 88888 in reaped, "orphan PID 88888 was not reaped on start()"
        finally:
            daemon_hold.set()


def test_stop_reaps_orphan_from_pid_file(agent, tmp_path):
    """Even if the in-process Popen handle is None (server-restart case),
    stop() must reach the orphan daemon via the PID file."""
    (tmp_path / "playit.pid").write_text("77777")

    reaped = []

    def fake_is_alive(pid):
        return pid == 77777 and 77777 not in reaped

    def fake_reap(pid):
        reaped.append(pid)

    with patch.object(agent, "_is_pid_alive", side_effect=fake_is_alive), \
         patch.object(agent, "_reap_pid",     side_effect=fake_reap):
        agent.stop()

    assert 77777 in reaped, "stop() did not reap orphan via PID file"
    assert not (tmp_path / "playit.pid").exists(), "PID file should be cleared after reap"
