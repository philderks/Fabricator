"""JSON-based storage for server data."""
import json
import os
import shutil
import threading
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.core.config import get_config
from backend.utils.time import iso_z_now


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

        now_iso = iso_z_now()
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
                server['updatedAt'] = iso_z_now()
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


# ── Installed-content manifest ─────────────────────────────────────────
# Maps a jar filename in the server's mods/ or plugins/ folder to the
# Modrinth project it came from. Recorded at install time because project
# identity cannot be recovered from the filename afterwards: plugin authors
# routinely ship a jar whose name has nothing to do with the project slug
# (`simple-voice-chat` -> `voicechat-bukkit-2.6.20.jar`), so the old
# filename-prefix guess mislabelled roughly a quarter of real plugins as
# not-installed. Filenames are the key because that is the only identifier
# the mods-list route (a plain directory scan) can produce.

CONTENT_MANIFEST_KEY = 'modContent'


def get_content_manifest(server_id: str) -> Dict[str, Any]:
    """Return ``{filename: entry}`` for a server, or ``{}`` if none/unknown."""
    server = get_server(server_id)
    if not server:
        return {}
    manifest = server.get(CONTENT_MANIFEST_KEY)
    return manifest if isinstance(manifest, dict) else {}


def record_content_install(server_id: str, filename: str, entry: Dict[str, Any]) -> None:
    """Record that ``filename`` was installed from a Modrinth project.

    Read-modify-writes the manifest under ``_storage_lock`` rather than via
    ``get_server`` + ``update_server``, so two concurrent installs into the
    same server cannot drop each other's entry in the gap between the two
    calls.
    """
    with _storage_lock:
        servers = load_servers()
        for server in servers:
            if server.get('id') != server_id:
                continue
            manifest = server.get(CONTENT_MANIFEST_KEY)
            if not isinstance(manifest, dict):
                manifest = {}
            manifest[filename] = entry
            server[CONTENT_MANIFEST_KEY] = manifest
            server['updatedAt'] = iso_z_now()
            save_servers(servers)
            return


def forget_content(server_id: str, filenames: List[str]) -> None:
    """Drop manifest entries for ``filenames`` (deleted/replaced jars).

    Silently ignores names with no entry — hand-dropped jars never had one.
    """
    if not filenames:
        return
    with _storage_lock:
        servers = load_servers()
        for server in servers:
            if server.get('id') != server_id:
                continue
            manifest = server.get(CONTENT_MANIFEST_KEY)
            if not isinstance(manifest, dict):
                return
            removed = False
            for filename in filenames:
                if manifest.pop(filename, None) is not None:
                    removed = True
            if removed:
                server[CONTENT_MANIFEST_KEY] = manifest
                server['updatedAt'] = iso_z_now()
                save_servers(servers)
            return


def clear_content_manifest(server_id: str) -> None:
    """Wipe the whole manifest — for flows that replace the folder wholesale
    (e.g. a clean modpack install)."""
    with _storage_lock:
        servers = load_servers()
        for server in servers:
            if server.get('id') != server_id:
                continue
            if not server.get(CONTENT_MANIFEST_KEY):
                return
            server[CONTENT_MANIFEST_KEY] = {}
            server['updatedAt'] = iso_z_now()
            save_servers(servers)
            return
