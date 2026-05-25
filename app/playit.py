"""playit.gg agent lifecycle manager.

Manages the playit agent as a child process of the Flask application.
All Flask imports are intentionally absent — this is pure Python so it can
be unit-tested and imported without an application context.

State machine
-------------
stopped  ──start()──► starting ──claim line──► claiming ──address line──► connected
   ▲                                                                           │
   └───────────────────────stop() / clean exit────────────────────────────────┘
                                        error  ◄── non-zero exit ──────────────┘
"""

from __future__ import annotations

import logging
import os
import re
import signal
import subprocess
import threading
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_PLAYIT_BIN = "/usr/bin/playit"
_SECRET_FILE = "/var/lib/fabricator/playit.toml"

_RE_CLAIM_URL = re.compile(r"claim_url=(\S+)")
_RE_ADDRESS   = re.compile(r"(\S+\.ply\.gg:\d+)")

# ---------------------------------------------------------------------------
# Module-level shared state
# ---------------------------------------------------------------------------

_lock:      threading.Lock      = threading.Lock()
_proc:      Optional[subprocess.Popen] = None   # type: ignore[type-arg]
_status:    str                 = "stopped"      # stopped|starting|claiming|connected|error
_address:   Optional[str]       = None
_claim_url: Optional[str]       = None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def start() -> None:
    """Launch the playit agent process if it is not already running.

    Spawns a background daemon thread that reads stdout and updates the
    shared state machine as the agent progresses through its lifecycle.
    Calling ``start()`` while a process is already alive is a no-op.
    """
    global _proc, _status, _address, _claim_url

    with _lock:
        if _proc is not None and _proc.poll() is None:
            logger.debug("playit agent is already running (pid=%d); ignoring start()", _proc.pid)
            return

        cmd = [_PLAYIT_BIN, "--stdout"]
        if os.path.exists(_SECRET_FILE):
            cmd += ["--secret", _SECRET_FILE]
            logger.info("playit: using secret file %s", _SECRET_FILE)
        else:
            logger.info("playit: no secret file found at %s — agent will emit a claim URL", _SECRET_FILE)

        logger.info("playit: launching %s", " ".join(cmd))
        _proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,   # merge stderr into stdout
            text=True,
            preexec_fn=os.setsid,       # new process group so we can kill the tree
        )

        _status    = "starting"
        _address   = None
        _claim_url = None

    reader = threading.Thread(target=_read_stdout, args=(_proc,), daemon=True, name="playit-stdout")
    reader.start()
    logger.info("playit: process started (pid=%d)", _proc.pid)


def stop() -> None:
    """Terminate the playit agent process and reset status to ``"stopped"``."""
    global _proc, _status

    with _lock:
        proc = _proc
        if proc is None or proc.poll() is not None:
            logger.debug("playit: stop() called but no running process")
            _status = "stopped"
            return

        try:
            pgid = os.getpgid(proc.pid)
            os.killpg(pgid, signal.SIGTERM)
            logger.info("playit: sent SIGTERM to process group %d", pgid)
        except ProcessLookupError:
            logger.debug("playit: process already gone before SIGTERM")
        except OSError as exc:
            logger.warning("playit: error sending SIGTERM: %s", exc)

        _status = "stopped"


def get_status() -> dict:
    """Return a snapshot of the current agent state.

    Returns
    -------
    dict with keys:
        ``status``    — one of ``"stopped"``, ``"starting"``, ``"claiming"``,
                        ``"connected"``, ``"error"``
        ``address``   — public ``host:port`` string when connected, else ``None``
        ``claim_url`` — URL the user must visit to claim the tunnel, else ``None``
    """
    with _lock:
        return {
            "status":    _status,
            "address":   _address,
            "claim_url": _claim_url,
        }


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _read_stdout(proc: subprocess.Popen) -> None:  # type: ignore[type-arg]
    """Read lines from *proc* stdout and advance the state machine.

    Intended to run on a dedicated daemon thread.  Exits when the process
    closes its stdout (i.e. terminates), then sets final status.
    """
    global _status, _address, _claim_url

    assert proc.stdout is not None, "_read_stdout called with a process that has no stdout pipe"

    for raw_line in proc.stdout:
        line = raw_line.rstrip()
        if not line:
            continue

        logger.debug("playit stdout: %s", line)

        # --- claim URL ---------------------------------------------------------
        m_claim = _RE_CLAIM_URL.search(line)
        if m_claim:
            url = m_claim.group(1)
            logger.info("playit: claim URL received — %s", url)
            with _lock:
                _claim_url = url
                _status    = "claiming"
            continue

        # --- public address ----------------------------------------------------
        m_addr = _RE_ADDRESS.search(line)
        if m_addr:
            addr = m_addr.group(1)
            logger.info("playit: tunnel connected — %s", addr)
            with _lock:
                _address   = addr
                _claim_url = None
                _status    = "connected"
            continue

    # stdout closed — process has exited
    proc.wait()
    rc = proc.returncode
    logger.info("playit: process exited with return code %d", rc)

    with _lock:
        final = "error" if rc != 0 else "stopped"
        _status = final
        logger.debug("playit: final status → %s", final)
