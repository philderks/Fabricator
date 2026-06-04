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
        agent_mod._address       = None
        agent_mod._claim_url     = None
        agent_mod._error_reason  = None
        agent_mod._gen           = 0

    yield agent_mod

    # Teardown: best-effort stop any lingering subprocesses started by tests.
    try:
        agent_mod.stop()
    except Exception:
        pass


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

    Status stops at "starting" because address-discovery via daemon stdout is
    intentionally disabled (the daemon does not log addresses to stdout in
    v1.0.5; the connected path will be wired through `playit-cli attach -s`
    once the event format is observed against a real claim).
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
    assert final["address"] is None
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
        agent._status = "connected"
        agent._address = "alpha.ply.gg:1"

    # Fake an old proc that has already exited non-zero.
    old_proc = MagicMock(spec=subprocess.Popen)
    old_proc.stdout = iter([])
    old_proc.wait.return_value = -15
    old_proc.returncode = -15

    # my_gen=4 < current _gen=5 → reader must silently exit.
    agent._read_daemon_stdout(old_proc, my_gen=4)

    status = agent.get_status()
    assert status["status"] == "connected", \
        f"stale reader corrupted state: {status}"
    assert status["address"] == "alpha.ply.gg:1"


def test_stop_then_late_reader_does_not_set_error(agent):
    """stop() bumps gen; a slow reader of the now-dead proc must noop."""
    with agent._lock:
        agent._gen = 1
        agent._status = "connected"

    agent.stop()  # bumps _gen to 2, sets status=stopped

    # Old reader from gen=1 wakes up.
    old_proc = MagicMock(spec=subprocess.Popen)
    old_proc.stdout = iter([])
    old_proc.wait.return_value = -15
    old_proc.returncode = -15
    agent._read_daemon_stdout(old_proc, my_gen=1)

    assert agent.get_status()["status"] == "stopped"


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


def _rundata_active_response(address="alpha.gl.joinmc.link"):
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


def _rundata_disabled_response(reason="legal-review"):
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


def test_rundata_active_tunnel_transitions_to_connected(agent, tmp_path, monkeypatch):
    """rundata returns a tunnel with display_address → status=connected, address set."""
    daemon_hold = threading.Event()
    fake_daemon, _, patches = _spawn_daemon_with_rundata(
        agent, tmp_path, _rundata_active_response("beta.gl.joinmc.link"), daemon_hold, monkeypatch,
    )

    with patches[0], patches[1], patches[2], patches[3]:
        try:
            agent.start()
            assert _wait_for(lambda: agent.get_status()["status"] == "connected", timeout=2.0), \
                f"never reached connected; got {agent.get_status()}"
            assert agent.get_status()["address"] == "beta.gl.joinmc.link"
        finally:
            daemon_hold.set()


def test_rundata_empty_tunnels_transitions_to_needs_tunnel(agent, tmp_path, monkeypatch):
    """Empty tunnels[] → status=needs_tunnel (actionable, NOT error)."""
    daemon_hold = threading.Event()
    fake_daemon, _, patches = _spawn_daemon_with_rundata(
        agent, tmp_path, _rundata_empty_response(), daemon_hold, monkeypatch,
    )

    with patches[0], patches[1], patches[2], patches[3]:
        try:
            agent.start()
            assert _wait_for(lambda: agent.get_status()["status"] == "needs_tunnel", timeout=2.0), \
                f"never reached needs_tunnel; got {agent.get_status()}"
            assert agent.get_status()["address"] is None
            assert agent.get_status()["error_reason"] is None
        finally:
            daemon_hold.set()


def test_rundata_disabled_reason_transitions_to_error(agent, tmp_path, monkeypatch):
    """disabled_reason set → status=error with that reason."""
    daemon_hold = threading.Event()
    fake_daemon, _, patches = _spawn_daemon_with_rundata(
        agent, tmp_path, _rundata_disabled_response("policy-violation"), daemon_hold, monkeypatch,
    )

    with patches[0], patches[1], patches[2], patches[3]:
        try:
            agent.start()
            assert _wait_for(lambda: agent.get_status()["status"] == "error", timeout=2.0), \
                f"never reached error; got {agent.get_status()}"
            assert "policy-violation" in (agent.get_status()["error_reason"] or "")
        finally:
            daemon_hold.set()


def test_rundata_network_failure_keeps_neutral_running(agent, tmp_path, monkeypatch):
    """API unreachable → status=running (neutral), NOT error."""
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
            # Crucially, this is NOT an error — no red UI.
            assert agent.get_status()["status"] != "error"
            assert agent.get_status()["error_reason"] is None
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

    assert result is None
    assert secret not in caplog.text, "SECRET LEAK via rundata error path"
    for rec in caplog.records:
        assert secret not in rec.getMessage()
        assert secret not in str(rec.args)


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
