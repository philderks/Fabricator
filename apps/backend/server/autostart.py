"""Auto-start Minecraft servers on Fabricator boot.

Each server record carries an ``autoStart`` mode:

* ``"always"`` — start the server every time Fabricator starts.
* ``"never"``  — never start automatically (the default for existing records).
* ``"last"``   — restore the previous run state: start only if the server was
                 running when Fabricator last exited (a clean shutdown, a crash,
                 or a host reboot all leave the persisted status at ``running``,
                 since the graceful-stop path stops the JVM without rewriting
                 ``servers.json``).

The decision snapshot is read synchronously at boot *before* the HTTP server
starts serving — once the dashboard lists servers, ``_augment_with_runtime``
reconciles a stale ``running`` back to ``stopped``, which would erase the
"was running" signal that ``"last"`` mode depends on. The actual JVM launches
run on background threads so a slow start can't delay the tray / serve loop.
"""
from __future__ import annotations

import logging
import threading
from typing import Dict

logger = logging.getLogger(__name__)

VALID_MODES = ('always', 'never', 'last')
DEFAULT_MODE = 'never'

# A server is only auto-startable once it is installed. Records still in
# pending / installing / failed are skipped regardless of mode.
_RUNNABLE_STATUSES = {'stopped', 'running'}


def normalize_mode(mode: object) -> str:
    """Coerce an arbitrary value to a valid mode, defaulting to ``never``."""
    value = str(mode or DEFAULT_MODE).lower()
    return value if value in VALID_MODES else DEFAULT_MODE


def _should_start(server: Dict[str, object]) -> bool:
    status = str(server.get('status') or '').lower()
    if status not in _RUNNABLE_STATUSES:
        return False
    mode = normalize_mode(server.get('autoStart'))
    if mode == 'always':
        return True
    if mode == 'last':
        return status == 'running'
    return False


def _start_one(server: Dict[str, object]) -> None:
    from backend.server import storage
    from backend.server.java_compat import resolve_required_java, skip_java_enforcement
    from backend.server.registry import get_server_process_registry

    server_id = str(server.get('id'))
    try:
        compat = resolve_required_java(str(server.get('version') or ''))
        required = compat.required_java if compat.enforceable else None
        if skip_java_enforcement():
            required = None

        result = get_server_process_registry().start_server(
            server, required_java_major=required
        )
        status = result.get('status')
        if status:
            storage.update_server_status(server_id, status)
        if status == 'running':
            logger.info("auto-start: %s is running", server_id)
        else:
            logger.warning(
                "auto-start: %s did not start (%s)",
                server_id, result.get('message') or 'unknown error',
            )
    except Exception as exc:  # one server must never block the others
        logger.warning("auto-start: %s failed: %s", server_id, exc)


def autostart_servers() -> None:
    """Start servers per their ``autoStart`` mode.

    Reads the server list synchronously (capturing the persisted run state
    before anything reconciles it), then launches each target on its own
    daemon thread. Safe to call once during boot.
    """
    from backend.server import storage

    try:
        servers = storage.get_all_servers()
    except Exception as exc:
        logger.warning("auto-start: could not load servers: %s", exc)
        return

    targets = [s for s in servers if _should_start(s)]
    if not targets:
        return

    logger.info(
        "auto-start: launching %d server(s): %s",
        len(targets), [s.get('id') for s in targets],
    )
    for server in targets:
        threading.Thread(
            target=_start_one,
            args=(server,),
            name=f"autostart-{server.get('id')}",
            daemon=True,
        ).start()
