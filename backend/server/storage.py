"""JSON-based storage for server data."""
import json
import os
import shutil
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.core.config import get_config


def _resolve_servers_file() -> Path:
    """Resolve the servers.json path from the current environment.

    Called at every access, not cached at module import — so that env vars
    changed after import (tests, late `.env` load, `sys._MEIPASS` rebinds)
    take effect.
    """
    config = get_config()
    configured = getattr(config, 'SERVERS_FILE', 'servers.json')
    return Path(configured).expanduser()


def _legacy_servers_file() -> Path:
    return Path.cwd() / "servers.json"


class _LazyServersFile:
    """Module-level proxy that forwards attribute access to a fresh Path.

    This lets existing call sites (``storage.SERVERS_FILE.parent``,
    ``storage.SERVERS_FILE.write_text(...)``, etc.) keep working without
    a broader API change, while resolving the concrete Path lazily.
    """

    def __getattr__(self, name):
        return getattr(_resolve_servers_file(), name)

    def __fspath__(self):
        return str(_resolve_servers_file())

    def __str__(self):
        return str(_resolve_servers_file())

    def __repr__(self):
        return f"_LazyServersFile({_resolve_servers_file()!r})"


SERVERS_FILE = _LazyServersFile()
_storage_lock = threading.Lock()


def _ensure_file_exists():
    """Create servers.json if it doesn't exist."""
    SERVERS_FILE.parent.mkdir(parents=True, exist_ok=True)

    # One-time migration from the historical cwd-based location. Copy, never
    # move: a test (or any sibling process) running from the repo root can
    # resolve SERVERS_FILE to a tmp path while legacy still points at the
    # live /workspaces/.../servers.json — `move` would then destroy the live
    # data when the tmp dir is cleaned up.
    legacy = _legacy_servers_file()
    if (
        not SERVERS_FILE.exists()
        and legacy != _resolve_servers_file()
        and legacy.exists()
    ):
        try:
            shutil.copy2(str(legacy), str(SERVERS_FILE))
            return
        except OSError:
            pass

    if not SERVERS_FILE.exists():
        SERVERS_FILE.write_text("[]", encoding='utf-8')


def load_servers() -> List[Dict[str, Any]]:
    """Load all servers from JSON file.

    Raises:
        json.JSONDecodeError if the file exists but is corrupted. Callers
        must decide how to surface this to the user — silently returning []
        would cause the next save to overwrite genuine state with an empty
        list.
    """
    _ensure_file_exists()
    with open(SERVERS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_servers(servers: List[Dict[str, Any]]) -> None:
    """Save servers list to JSON file atomically.

    Writes to ``servers.json.tmp`` in the same directory, fsyncs, then
    ``os.replace`` swaps it into place. A crash between write and replace
    leaves the previous file intact; a crash after replace leaves the new
    one fully written. On any exception before the rename, the partial
    tmp file is removed.
    """
    target = SERVERS_FILE
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = target.with_suffix(target.suffix + ".tmp")

    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(servers, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, target)
    except Exception:
        # Remove the partial tmp file; let the caller see the original error.
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def generate_server_id() -> str:
    """Generate a unique server ID.

    Returns:
        Server ID string (e.g., 'srv_abc123')
    """
    return f"srv_{uuid.uuid4().hex[:8]}"


def get_all_servers() -> List[Dict[str, Any]]:
    """Get all servers.

    Returns:
        List of all servers
    """
    return load_servers()


def get_server(server_id: str) -> Optional[Dict[str, Any]]:
    """Get a specific server by ID.

    Args:
        server_id: Server ID

    Returns:
        Server dictionary or None if not found
    """
    servers = load_servers()
    return next((s for s in servers if s.get('id') == server_id), None)


def create_server(server_data: Dict[str, Any]) -> Dict[str, Any]:
    """Create a new server.

    Args:
        server_data: Server configuration data

    Returns:
        Created server with generated ID and metadata
    """
    with _storage_lock:
        servers = load_servers()

        now_iso = datetime.utcnow().isoformat() + 'Z'
        new_server = {
            'id': generate_server_id(),
            'status': 'stopped',
            'createdAt': now_iso,
            'updatedAt': now_iso,
            **server_data
        }

        servers.append(new_server)
        save_servers(servers)

        return new_server


def update_server(server_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Update an existing server.

    Args:
        server_id: Server ID
        updates: Dictionary of fields to update

    Returns:
        Updated server or None if not found
    """
    with _storage_lock:
        servers = load_servers()

        for server in servers:
            if server.get('id') == server_id:
                server.update(updates)
                server['updatedAt'] = datetime.utcnow().isoformat() + 'Z'
                save_servers(servers)
                return server

        return None


def delete_server(server_id: str) -> bool:
    """Delete a server.

    Args:
        server_id: Server ID

    Returns:
        True if deleted, False if not found
    """
    with _storage_lock:
        servers = load_servers()
        initial_count = len(servers)

        servers = [s for s in servers if s.get('id') != server_id]

        if len(servers) < initial_count:
            save_servers(servers)
            return True

        return False


def update_server_status(server_id: str, status: str) -> Optional[Dict[str, Any]]:
    """Update server status.

    Args:
        server_id: Server ID
        status: New status ('stopped', 'starting', 'running', 'stopping')

    Returns:
        Updated server or None if not found
    """
    return update_server(server_id, {'status': status})
