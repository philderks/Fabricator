"""playit.gg agent lifecycle: claim bootstrap, daemon supervision, status.

State machine (transitions only via start()/stop()/reset() or background threads):

    unsupported  ──── (Windows only — no playit support)
    stopped      ──── initial / after stop() / after reset()
    claiming     ──── claim URL is published AND the exchange subprocess is
                      blocking on the user's browser-approval.
    starting     ──── daemon Popen launched, rundata poll not yet completed.
    running      ──── daemon healthy, but no usable address yet (rundata
                      unreachable, or returned no tunnel-with-address). This
                      is NEUTRAL — the tunnel may still be live from the
                      daemon's side; we just lack confirmation. NOT an error.
    needs_tunnel ──── daemon healthy + rundata confirmed agent registered,
                      but tunnels[] is empty. User must allocate one in the
                      playit.gg dashboard. Actionable, not an error.
    connected    ──── rundata returned a tunnel with display_address and
                      disabled_reason=null — the address is in _address.
    error        ──── REAL failure only: disabled_reason non-null from
                      rundata, AgentDisabledOverLimit from daemon stdout,
                      or daemon process exited non-zero. Transient rundata
                      failures do NOT enter this state.

Race-freedom is enforced by a monotonic generation counter (`_gen`). Both
start() and stop() bump `_gen` under the lock. Every background thread
captures its `my_gen` at spawn and re-checks under the lock before mutating
shared state. If the generation has advanced, the thread silently exits —
this is what prevents:

    * a slow daemon-stdout reader of a stopped process from overwriting the
      freshly started one with "error" (restart race);
    * a `claim exchange` that returned successfully AFTER the user clicked
      OFF from writing the secret and silently bringing the tunnel live
      anyway (cancel-during-claim — see test in test_playit_agent.py).

The secret-bearing path is `_run_exchange_popen()`. It uses raw Popen
(not binary.run_cli) so stop() can terminate the long-running --wait. The
exchange stdout IS the secret key — it must not appear in any log record,
exception message, or repr. Callers re-bind `secret_value = None` immediately
after persisting it.
"""
from __future__ import annotations

import errno
import logging
import os
import re
import signal
import subprocess
import threading
import time
from collections import deque
from pathlib import Path
from typing import Deque, Optional

from backend.utils import platform as platform_utils

from . import binary as playit_binary

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------

_CLAIM_WAIT_SECONDS = 600        # `playit-cli claim exchange --wait N`
_COMMUNICATE_GRACE  = 5          # buffer on top of _CLAIM_WAIT_SECONDS
_STOP_TIMEOUT       = 5          # daemon graceful-shutdown window
_EXCHANGE_KILL_TIMEOUT = 2       # cancel-during-claim grace
_LOG_BUFFER_LINES   = 30         # ring buffer for daemon stdout — feeds error_reason

# rundata API — the single source of truth for tunnel address + state.
# Replaces the previous stdout-regex / attach-stream / watchdog approaches.
_API_BASE                  = "https://api.playit.gg"
_RUNDATA_PATH              = "/v1/agents/rundata"
_RUNDATA_INTERVAL_SECONDS  = 30        # address is static; no need to hammer the API
_RUNDATA_TIMEOUT_SECONDS   = 10
_RUNDATA_INITIAL_BACKOFF   = 1.5       # give the daemon time to register before first poll

# ANSI escape sequence stripper for the daemon's tracing output.
_RE_ANSI = re.compile(r"\x1b\[[0-9;]*m")
_RE_HEX_SECRET = re.compile(r"^[a-fA-F0-9]+$")

# Daemon-stdout error patterns. Each entry maps a substring match to a
# user-actionable message. Order matters — first match wins.
_DAEMON_ERROR_PATTERNS = [
    (
        "AgentDisabledOverLimit",
        "playit.gg account is at its free agent limit. "
        "Reset and use a different account, or remove an agent in your playit.gg dashboard.",
    ),
    (
        "agent disabled",
        "playit.gg disabled this agent. "
        "Open the playit.gg dashboard to check the agent state.",
    ),
    (
        "invalid secret",
        "playit secret is no longer valid. Reset and re-claim the agent.",
    ),
]

# ---------------------------------------------------------------------------
# Module-level shared state (always accessed under _lock)
# ---------------------------------------------------------------------------

_lock           = threading.RLock()
_proc:           Optional[subprocess.Popen] = None  # daemon
_exchange_proc:  Optional[subprocess.Popen] = None  # `playit-cli claim exchange`
_status         = "stopped"
_address:       Optional[str] = None
_claim_url:     Optional[str] = None
_error_reason:  Optional[str] = None
_gen            = 0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_status() -> dict:
    """Snapshot of the agent state. Safe to call from any thread."""
    if platform_utils.is_windows():
        return {
            "status": "unsupported",
            "address": None,
            "claim_url": None,
            "error_reason": "playit is not supported on Windows",
            "binary_verified": False,
        }
    with _lock:
        return {
            "status": _status,
            "address": _address,
            "claim_url": _claim_url,
            "error_reason": _error_reason,
            "binary_verified": playit_binary.binary_verified(),
        }


def is_enabled() -> bool:
    """Whether the tunnel should be running. The persisted state file written
    by set_enabled() is authoritative when present; otherwise fall back to the
    PLAYIT_ENABLED env var so env-driven installs keep working.

    Used by run.py auto-start so a tunnel toggled on from the dashboard
    survives a service restart.
    """
    try:
        return playit_binary.enabled_state_path().read_text().strip().lower() == "true"
    except FileNotFoundError:
        pass
    except OSError as exc:
        logger.warning("playit: could not read enabled-state file: %s", exc)
    return os.environ.get("PLAYIT_ENABLED", "").strip().lower() == "true"


def set_enabled(enabled: bool) -> None:
    """Persist the desired tunnel state so it survives a restart. Best-effort:
    a non-writable runtime dir (e.g. dev run outside systemd) logs a warning
    and leaves the env-var fallback in place rather than failing the request."""
    path = playit_binary.enabled_state_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("true" if enabled else "false")
    except OSError as exc:
        logger.warning("playit: could not persist enabled-state: %s", exc)


def start() -> None:
    """Launch the agent. If no secret exists, bootstraps via the claim flow.

    Returns immediately; lifecycle transitions are observable via get_status().
    Errors that can be surfaced to the user (binary missing, claim timeout)
    are written to _status="error" + _error_reason rather than raised.
    """
    if platform_utils.is_windows():
        return

    global _proc, _exchange_proc, _status, _address, _claim_url, _error_reason, _gen

    # Persist the desired state up front so an auto-start after restart knows
    # the tunnel was wanted. Done before the binary checks so even a failed
    # start (missing binary) remembers the user's intent to re-enable.
    set_enabled(True)

    # Orphan reap BEFORE bumping gen so we don't race with our own watchdog
    # of an old run. Safe to call even when no PID file exists.
    _reap_orphan_daemon()

    with _lock:
        if _proc is not None and _proc.poll() is None:
            logger.debug("playit: start() called but daemon already running (pid=%d)", _proc.pid)
            return
        _gen += 1
        my_gen = _gen
        _status = "starting"
        _address = None
        _claim_url = None
        _error_reason = None

    daemon = playit_binary.find_daemon()
    if daemon is None:
        with _lock:
            if my_gen != _gen:
                return
            _status = "error"
            _error_reason = (
                "playit daemon binary not found — run tools/install.sh "
                "or place it at /usr/local/bin/playit"
            )
        return

    if playit_binary.find_cli() is None:
        with _lock:
            if my_gen != _gen:
                return
            _status = "error"
            _error_reason = (
                "playit-cli binary not found — run tools/install.sh "
                "or place it at /usr/local/bin/playit-cli"
            )
        return

    threading.Thread(
        target=_lifecycle_thread,
        args=(my_gen, daemon),
        name=f"playit-lifecycle-{my_gen}",
        daemon=True,
    ).start()


def stop() -> None:
    """Stop the agent. Idempotent. Cancels in-flight claim flows."""
    if platform_utils.is_windows():
        return

    global _proc, _exchange_proc, _status, _address, _claim_url, _error_reason, _gen

    # Persist the user's intent so auto-start after a restart won't bring a
    # deliberately-stopped tunnel back up.
    set_enabled(False)

    with _lock:
        _gen += 1                # invalidate every in-flight thread
        proc = _proc
        exchange_proc = _exchange_proc
        _proc = None
        _exchange_proc = None
        _status = "stopped"
        _address = None
        _claim_url = None
        _error_reason = None

    # Terminations happen outside the lock — they may block briefly.
    if exchange_proc is not None and exchange_proc.poll() is None:
        try:
            exchange_proc.terminate()
            try:
                exchange_proc.wait(timeout=_EXCHANGE_KILL_TIMEOUT)
            except subprocess.TimeoutExpired:
                exchange_proc.kill()
        except OSError:
            pass

    if proc is not None and proc.poll() is None:
        try:
            if platform_utils.is_windows():
                proc.terminate()
            else:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                except ProcessLookupError:
                    pass
            try:
                proc.wait(timeout=_STOP_TIMEOUT)
            except subprocess.TimeoutExpired:
                proc.terminate()
                try:
                    proc.wait(timeout=_STOP_TIMEOUT)
                except subprocess.TimeoutExpired:
                    proc.kill()
        except OSError:
            pass

    # Defense-in-depth: if a PID file points at a still-alive daemon (typically
    # an orphan from a previous server run where the Popen handle was lost),
    # reap it too. This is what makes Reset actually reach the tunnel state
    # the user expects to have killed.
    orphan_pid = _read_pid_file()
    if orphan_pid is not None and _is_pid_alive(orphan_pid):
        logger.warning("playit: reaping orphan daemon PID %d during stop()", orphan_pid)
        _reap_pid(orphan_pid)
    _clear_pid_file()


def reset() -> None:
    """Stop the daemon and delete the persisted secret, forcing a re-claim.

    Order is load-bearing: stop() FIRST, then unlink. Deleting the secret
    while the daemon still holds it open would leak a live tunnel after the
    user explicitly clicked Reset.
    """
    stop()
    secret = playit_binary.secret_path()
    try:
        secret.unlink()
        logger.info("playit: secret file removed at %s", secret)
    except FileNotFoundError:
        pass
    except OSError as exc:
        logger.warning("playit: could not unlink secret %s: %s", secret, exc)


# ---------------------------------------------------------------------------
# Lifecycle thread — entry point for one full start() generation
# ---------------------------------------------------------------------------

def _lifecycle_thread(my_gen: int, daemon_bin: str) -> None:
    """Run the bootstrap-then-daemon sequence for a single generation."""
    secret = playit_binary.secret_path()

    if not secret.exists():
        if not _run_claim_bootstrap(my_gen, secret):
            return  # error_reason or stop already handled

    _run_daemon(my_gen, daemon_bin, secret)


# ---------------------------------------------------------------------------
# Claim bootstrap — secret-bearing path. KEEP CODE BELOW SECRET-AWARE.
# ---------------------------------------------------------------------------

def _run_claim_bootstrap(my_gen: int, secret: Path) -> bool:
    """Run `claim generate | url | exchange` and persist the secret.

    Returns True iff the secret file is now populated for `my_gen` and the
    caller should proceed to daemon launch. Returns False on any cancellation,
    error, or generation mismatch.
    """
    global _exchange_proc, _status, _claim_url, _error_reason

    try:
        code = playit_binary.run_cli("claim", "generate", timeout=10).stdout.strip()
        url  = playit_binary.run_cli("claim", "url", code, timeout=10).stdout.strip()
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError) as exc:
        with _lock:
            if my_gen != _gen:
                return False
            _status = "error"
            _error_reason = f"claim init failed: {type(exc).__name__}"
        return False

    if not code or not url:
        with _lock:
            if my_gen != _gen:
                return False
            _status = "error"
            _error_reason = "claim init returned empty code or URL"
        return False

    with _lock:
        if my_gen != _gen:
            return False
        _status = "claiming"
        _claim_url = url

    return _run_exchange_popen(my_gen, code, secret)


def _run_exchange_popen(my_gen: int, code: str, secret: Path) -> bool:
    """Spawn `playit-cli claim exchange CODE --wait N` and persist its stdout.

    The stdout of this subprocess IS the secret key. It must not be logged,
    raised in an exception, or formatted into any string we emit. Any
    deviation from this is a security regression.
    """
    global _exchange_proc, _status, _error_reason

    cli = playit_binary.find_cli()
    if cli is None:
        with _lock:
            if my_gen != _gen:
                return False
            _status = "error"
            _error_reason = "playit-cli binary missing during exchange"
        return False

    try:
        exchange = subprocess.Popen(
            [cli, "claim", "exchange", code, "--wait", str(_CLAIM_WAIT_SECONDS)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            **platform_utils.subprocess_no_window_kwargs(),
        )
    except OSError as exc:
        with _lock:
            if my_gen != _gen:
                return False
            _status = "error"
            _error_reason = f"could not spawn claim exchange: {exc}"
        return False

    with _lock:
        if my_gen != _gen:
            try:
                exchange.terminate()
            except OSError:
                pass
            return False
        _exchange_proc = exchange
        # Status stays "claiming" while exchange.communicate() blocks — that
        # IS the user-action phase, and the frontend's claim banner is the
        # only way the user discovers the URL. Flipping to a status that
        # hides the URL here means the URL was never actually shown, the
        # user never clicks, and the exchange times out after 10 min.

    secret_value: Optional[str] = None
    try:
        # NOTE: we capture stdout into `secret_value` and stderr into _err.
        # _err is allowed in logs only because playit-cli writes claim
        # status/diagnostics there, NEVER the secret.
        secret_value, _err = exchange.communicate(timeout=_CLAIM_WAIT_SECONDS + _COMMUNICATE_GRACE)
    except subprocess.TimeoutExpired:
        # Local kill — never touches secret_value (it is still None).
        try:
            exchange.kill()
            exchange.communicate(timeout=2)
        except (subprocess.TimeoutExpired, OSError):
            pass
        with _lock:
            _exchange_proc = None
            if my_gen != _gen:
                return False
            _status = "error"
            _error_reason = "claim timed out — try again"
        return False
    except OSError as exc:
        with _lock:
            _exchange_proc = None
            if my_gen != _gen:
                return False
            _status = "error"
            _error_reason = f"claim exchange OS error: {exc}"
        return False

    with _lock:
        _exchange_proc = None
        if my_gen != _gen:
            secret_value = None
            return False
        if exchange.returncode != 0:
            secret_value = None
            _status = "error"
            _error_reason = "claim exchange failed"   # no stdout/stderr in the reason
            return False

    # `claim exchange` writes a status reminder to stdout every 2 s while
    # polling ("Open this link to finish setting up playit:" / URL). On
    # success the secret token is appended last. We extract the trailing
    # non-empty line and reject obvious reminder lines so a successful
    # exchange that we mis-read can't end up writing the URL as the secret.
    # Verified against v1.0.5 playit-cli claim exchange source — see plan.
    try:
        secret_token = _extract_exchange_secret(secret_value or "")
    finally:
        secret_value = None

    if not secret_token:
        with _lock:
            if my_gen != _gen:
                return False
            _status = "error"
            _error_reason = "claim exchange returned no secret"
        return False

    try:
        _atomic_write_secret(secret, secret_token)
    finally:
        secret_token = None

    return True


def _extract_exchange_secret(raw: str) -> Optional[str]:
    """Pull the secret token out of `playit-cli claim exchange` stdout.

    The CLI prints a status reminder on every poll cycle:

        Open this link to finish setting up playit:
        https://playit.gg/claim/<code>

    On success the secret key is appended at the end. We take the last
    non-empty line and reject it if it still looks like the reminder block.
    """
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    if not lines:
        return None
    last = lines[-1]
    lowered = last.lower()
    if lowered.startswith("open this link") or lowered.startswith("http"):
        return None
    return last


def _atomic_write_secret(target: Path, content: str) -> None:
    """Write a sensitive value atomically with mode 0600.

    Uses a sibling temp file + os.replace so partial writes don't leave the
    daemon reading half a secret. chmod is applied to the temp file before
    rename so the rename never exposes a permissive file.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_str = _mkstemp_in(target.parent)
    tmp = Path(tmp_str)
    try:
        try:
            os.fchmod(fd, 0o600)
        except OSError:
            pass
        with os.fdopen(fd, "w") as f:
            f.write(content)
        os.replace(tmp, target)
    except Exception:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass
        raise


def _mkstemp_in(directory: Path) -> tuple[int, str]:
    """Wrapper around tempfile.mkstemp so tests can monkeypatch it."""
    import tempfile
    return tempfile.mkstemp(prefix=".playit-secret-", dir=str(directory))


# ---------------------------------------------------------------------------
# Daemon supervision
# ---------------------------------------------------------------------------

def _run_daemon(my_gen: int, daemon_bin: str, secret: Path) -> None:
    """Spawn the playit daemon and stream stdout for address + failure events.

    `--log-path` is intentionally NOT passed. With it, the daemon redirects all
    `tracing` output to the file and our stdout pipe stays empty — the reader
    then blocks forever and never surfaces useful error_reason. Without it, the
    daemon writes to stdout (merged with stderr by Popen), feeding the reader
    a single coherent stream we can both parse for events and tail for errors.
    """
    global _proc, _status, _error_reason

    socket = playit_binary.socket_path()

    try:
        socket.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass

    cmd = [
        daemon_bin,
        "--secret-path", str(secret),
        "--socket-path", str(socket),
    ]

    popen_kwargs = dict(
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        **platform_utils.subprocess_no_window_kwargs(),
    )
    if not platform_utils.is_windows():
        popen_kwargs["preexec_fn"] = os.setsid

    try:
        proc = subprocess.Popen(cmd, **popen_kwargs)
    except OSError as exc:
        with _lock:
            if my_gen != _gen:
                return
            _status = "error"
            _error_reason = f"daemon spawn failed: {exc}"
        return

    with _lock:
        if my_gen != _gen:
            # Already cancelled — terminate the freshly spawned daemon.
            try:
                proc.terminate()
            except OSError:
                pass
            return
        _proc = proc
        _status = "starting"

    # Persist PID so a future server restart can reap the daemon even if the
    # Popen handle is lost (orphan-protection, see _reap_orphan_daemon).
    _write_pid_file(proc.pid)

    # Kick off the rundata poller — the SINGLE source for address + tunnel
    # state. It runs in parallel with the stdout reader: rundata covers
    # connected/needs_tunnel, the reader covers AgentDisabledOverLimit-style
    # failures from the daemon's own log.
    _start_rundata_poller(my_gen)

    _read_daemon_stdout(proc, my_gen)

    # Reader exited (proc closed stdout). Clear the PID file so the next
    # start() doesn't try to reap a no-longer-relevant process.
    _clear_pid_file()


def _read_daemon_stdout(proc: subprocess.Popen, my_gen: int) -> None:
    """Stream daemon stdout — surface failures the rundata poller can't see.

    Address discovery moved entirely to the rundata HTTP poller (see
    _start_rundata_poller). This reader is now only responsible for:

    1. Buffering the last N ANSI-stripped lines so a daemon exit with a
       non-zero rc surfaces the real cause in error_reason, not a bare
       "exited with code N".

    2. Inline failure detection for AgentDisabledOverLimit-class errors that
       the daemon RETRIES forever rather than exiting on. Without this, the
       account-over-limit case would just look like a stuck "running" status
       because rundata still returns a (disabled) tunnel record. The stdout
       pattern is the earliest signal we have.
    """
    global _status, _address, _claim_url, _error_reason

    assert proc.stdout is not None
    log_buffer: Deque[str] = deque(maxlen=_LOG_BUFFER_LINES)

    for raw_line in proc.stdout:
        clean = _strip_ansi(raw_line).rstrip()
        if not clean:
            continue
        log_buffer.append(clean)
        logger.debug("playitd: %s", clean)

        matched = _match_daemon_error(clean)
        if matched is not None:
            with _lock:
                if my_gen != _gen:
                    return
                if _status != "error":
                    _status = "error"
                    _error_reason = matched
                    _claim_url = None
                    _address = None
                    logger.info("playit: daemon reported failure: %s", matched)

    proc.wait()
    rc = proc.returncode

    with _lock:
        if my_gen != _gen:
            return                       # newer generation owns the state
        # If we already set error via inline pattern, preserve it.
        if _status == "error" and _error_reason:
            return
        if rc == 0:
            _status = "stopped"
        else:
            tail = _tail_warn_line(log_buffer) or f"playitd exited with code {rc}"
            _status = "error"
            _error_reason = tail


def _strip_ansi(s: str) -> str:
    """Remove ANSI color/style escapes from a daemon log line."""
    return _RE_ANSI.sub("", s)


def _match_daemon_error(line: str) -> Optional[str]:
    """Map a known failure substring to a user-actionable message, or None."""
    for needle, message in _DAEMON_ERROR_PATTERNS:
        if needle in line:
            return message
    return None


def _tail_warn_line(buffer: Deque[str]) -> Optional[str]:
    """Pull the most useful line from the daemon log buffer for error_reason.

    Prefer the most recent WARN/ERROR line. Fall back to the last line if
    none are tagged. Returns None for empty buffers.
    """
    if not buffer:
        return None
    for line in reversed(buffer):
        if " WARN " in line or " ERROR " in line or "warning" in line.lower() or "error" in line.lower():
            return line[:280]            # cap for UI; longer lines go to logs
    return buffer[-1][:280]


# ---------------------------------------------------------------------------
# rundata API poller — single source of truth for tunnel address + state
# ---------------------------------------------------------------------------
# Replaces the old stdout-regex / attach-stream / starting-watchdog combo.
# Endpoint + auth scheme verified against the live API on 2026-05-29 and
# confirmed against v1.0.5 source (packages/playitd/src/daemon.rs +
# packages/api_client/src/lib.rs).
#
# Security: the agent secret is read fresh from the runtime dir on every
# poll cycle (so a reset+restart picks up the new secret) and never logged.
# The "Agent-Key <hex>" Authorization header is constructed locally and only
# attached to outgoing requests — same discipline as the claim exchange.

def _start_rundata_poller(my_gen: int) -> None:
    threading.Thread(
        target=_rundata_poller,
        args=(my_gen,),
        name=f"playit-rundata-{my_gen}",
        daemon=True,
    ).start()


def _rundata_poller(my_gen: int) -> None:
    """Long-running poller — owns transitions to/out of connected, running,
    needs_tunnel, and error (for disabled_reason). Gen-token disciplined."""
    global _status

    # Give the daemon a moment to authenticate with the playit API before the
    # first call, otherwise we'd just get a 401 for the first cycle.
    if not _sleep_with_gen(my_gen, _RUNDATA_INITIAL_BACKOFF):
        return

    while True:
        secret = _read_secret_for_api()
        body = _call_rundata(secret) if secret else None
        # Drop the secret reference as soon as the request returns —
        # defense-in-depth against late logging in the same scope.
        secret = None

        with _lock:
            if my_gen != _gen:
                return
            if body is not None:
                _apply_rundata_to_state(body)
            else:
                # Transient: if we're still in the brief post-spawn "starting"
                # window, transition to neutral "running" so the UI doesn't
                # hang on a loading state indefinitely. If we were already in
                # running / connected / needs_tunnel / error, don't touch it.
                if _status == "starting":
                    _status = "running"

        if not _sleep_with_gen(my_gen, _RUNDATA_INTERVAL_SECONDS):
            return


def _sleep_with_gen(my_gen: int, seconds: float) -> bool:
    """Sleep in 0.5s chunks so stop()/restart kicks the poller out promptly.

    Returns True if the full sleep elapsed under the same generation,
    False if a newer generation has taken over.
    """
    deadline = time.monotonic() + seconds
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return True
        with _lock:
            if my_gen != _gen:
                return False
        time.sleep(min(0.5, remaining))


def _read_secret_for_api() -> Optional[str]:
    """Read the agent secret from disk for an API call. Sanity-check the
    shape so a garbled file doesn't get sent over the wire."""
    try:
        raw = playit_binary.secret_path().read_text()
    except OSError:
        return None
    s = raw.strip()
    if not _RE_HEX_SECRET.match(s) or len(s) < 32:
        return None
    return s


def _call_rundata(secret: str) -> Optional[dict]:
    """One POST to /v1/agents/rundata. Returns parsed body or None on any
    transient error. Secret and Authorization header are NEVER logged,
    NEVER included in exception messages."""
    import urllib.request
    import urllib.error
    import json as _json

    req = urllib.request.Request(
        _API_BASE + _RUNDATA_PATH,
        data=b"{}",
        headers={
            "Content-Type": "application/json",
            "Authorization": "Agent-Key " + secret,  # value goes out, never to log
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=_RUNDATA_TIMEOUT_SECONDS) as resp:
            payload = resp.read()
    except urllib.error.HTTPError as e:
        # Status code is safe to log; the response body could echo our
        # request which carried the secret, so we deliberately do NOT touch
        # e.read() here.
        logger.debug("playit: rundata HTTP %d", e.code)
        return None
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        # Same pattern: log type, never the args (which may contain the URL
        # + Auth header in some Python builds).
        logger.debug("playit: rundata network error: %s", type(e).__name__)
        return None

    try:
        return _json.loads(payload.decode("utf-8", "replace"))
    except _json.JSONDecodeError:
        logger.debug("playit: rundata returned non-JSON body")
        return None


def _apply_rundata_to_state(body: dict) -> None:
    """Translate a rundata response into our state machine. Caller holds _lock.

    Tunnel-selection rule (matches what we saw in the live response):
      - Prefer the first tunnel with display_address AND disabled_reason=null
        → connected.
      - If all tunnels are disabled, surface the first disabled_reason
        → error.
      - If tunnels[] is empty → needs_tunnel (actionable).
      - If tunnels exist but none has an address and none is disabled (e.g.
        pending setup) → running (neutral).
    """
    global _status, _address, _error_reason

    # Don't overwrite an inline AgentDisabled error that the stdout reader
    # already surfaced — that signal is faster and more specific.
    if _status == "error" and _error_reason and _is_inline_failure(_error_reason):
        return

    data = (body or {}).get("data") or {}
    tunnels = data.get("tunnels") or []

    if not tunnels:
        _status = "needs_tunnel"
        _address = None
        _error_reason = None
        return

    active = None
    disabled = None
    for t in tunnels:
        if not isinstance(t, dict):
            continue
        if t.get("disabled_reason"):
            disabled = disabled or t
        elif t.get("display_address"):
            active = active or t

    if active:
        _status = "connected"
        _address = active["display_address"]
        _error_reason = None
        return

    if disabled:
        _status = "error"
        _address = None
        _error_reason = "playit tunnel disabled: " + str(disabled.get("disabled_reason"))
        return

    # Tunnels listed but neither active-with-address nor disabled — pending
    # setup. Stay neutral, don't pretend we have an address.
    _status = "running"
    _address = None


def _is_inline_failure(reason: Optional[str]) -> bool:
    """True iff `reason` came from our stdout pattern matcher (so we don't
    let a slow rundata response stamp over the faster signal)."""
    if not reason:
        return False
    return any(message == reason for _needle, message in _DAEMON_ERROR_PATTERNS)


# ---------------------------------------------------------------------------
# PID file — orphan-daemon protection across server restarts (Target 1b)
# ---------------------------------------------------------------------------
# Without this, if the Python server is restarted while the daemon is alive,
# the Popen handle is lost. The daemon's PPID becomes 1 (init) and no future
# stop()/reset() can reach it — the tunnel stays open after the user clicked
# "stopped". Persisting the PID to a file under the runtime dir lets a fresh
# server reap the orphan on next start().

def _pid_file_path() -> Path:
    return playit_binary.runtime_dir() / "playit.pid"


def _write_pid_file(pid: int) -> None:
    path = _pid_file_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        # Atomic write: a concurrent reader (e.g. the reaper, or a test polling
        # for the file) must never observe a truncated/empty file mid-write.
        # write_text() truncates then writes, leaving a window where the file
        # exists but is empty; os.replace() swaps in fully-written content.
        tmp = path.with_suffix(".pid.tmp")
        tmp.write_text(str(pid))
        os.replace(tmp, path)
    except OSError as exc:
        logger.warning("playit: could not write PID file %s: %s", path, exc)


def _read_pid_file() -> Optional[int]:
    try:
        return int(_pid_file_path().read_text().strip())
    except (FileNotFoundError, ValueError, OSError):
        return None


def _clear_pid_file() -> None:
    try:
        _pid_file_path().unlink()
    except FileNotFoundError:
        pass
    except OSError as exc:
        logger.debug("playit: could not unlink PID file: %s", exc)


def _is_pid_alive(pid: int) -> bool:
    """Linux-only liveness check via signal 0."""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        # Process exists but we can't signal it — treat as alive so we don't
        # reuse the PID assumption.
        return True
    except OSError as exc:
        if exc.errno == errno.ESRCH:
            return False
        return True


def _reap_pid(pid: int) -> None:
    """SIGTERM-then-SIGKILL a known daemon PID. Best effort."""
    if pid <= 0 or not _is_pid_alive(pid):
        return
    try:
        # Target the process group if we started it with setsid, otherwise the
        # raw PID — works regardless of who spawned it (we may have inherited
        # the orphan from a previous server run).
        try:
            os.killpg(os.getpgid(pid), signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            os.kill(pid, signal.SIGTERM)
    except OSError:
        return

    # Wait up to _STOP_TIMEOUT seconds for the process to exit.
    deadline = time.monotonic() + _STOP_TIMEOUT
    while time.monotonic() < deadline:
        if not _is_pid_alive(pid):
            return
        time.sleep(0.2)

    # Still alive — escalate to SIGKILL.
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        pass


def _reap_orphan_daemon() -> None:
    """If the PID file points at a live daemon we don't own, terminate it.

    Called from start() before spawning a new daemon so we never end up with
    two daemons fighting over the same socket/secret.
    """
    pid = _read_pid_file()
    if pid is None:
        return
    if _is_pid_alive(pid):
        logger.warning("playit: reaping orphan daemon PID %d from previous run", pid)
        _reap_pid(pid)
    _clear_pid_file()
