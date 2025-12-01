"""Process registry for managing per-server runtime state."""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Dict, Optional

from backend.core.config import get_config
from backend.server.manager import ServerManager


class ServerProcessRegistry:
    """Keeps track of ServerManager instances per server ID."""

    def __init__(self, base_dir: str | Path):
        self.base_dir = Path(base_dir).expanduser().resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._instances: Dict[str, ServerManager] = {}

    def _ensure_within_root(self, candidate: Path) -> Path:
        candidate = candidate.expanduser().resolve()
        try:
            candidate.relative_to(self.base_dir)
        except ValueError as exc:  # pragma: no cover - defensive guard
            raise ValueError(
                f"Install path '{candidate}' is outside of configured server root"
            ) from exc
        candidate.mkdir(parents=True, exist_ok=True)
        return candidate

    def _resolve_install_path(self, server: Dict[str, object]) -> Path:
        server_id = server.get('id')
        if not server_id:
            raise ValueError('Server entry is missing an id')

        raw_path = server.get('installPath')
        if raw_path:
            candidate = Path(str(raw_path))
            if not candidate.is_absolute():
                candidate = self.base_dir / candidate
        else:
            candidate = self.base_dir / str(server_id)

        return self._ensure_within_root(candidate)

    def _get_or_create_manager(self, server: Dict[str, object]) -> ServerManager:
        server_id = str(server['id'])
        with self._lock:
            manager = self._instances.get(server_id)
            if manager:
                return manager

            install_path = self._resolve_install_path(server)
            memory = server.get('memory', 4)
            command = server.get('command') or [
                'java',
                f'-Xms{memory}G',
                f'-Xmx{memory}G',
                '-jar',
                'server.jar',
                'nogui'
            ]
            manager = ServerManager(command=command, cwd=str(install_path))
            self._instances[server_id] = manager
            return manager

    def get_status(self, server_id: str) -> Dict[str, object]:
        with self._lock:
            manager = self._instances.get(server_id)
        if not manager:
            return {'status': 'stopped', 'message': 'Server process is not running'}
        return manager.status()

    def start_server(self, server: Dict[str, object]) -> Dict[str, object]:
        manager = self._get_or_create_manager(server)
        return manager.start()

    def stop_server(self, server_id: str) -> Dict[str, object]:
        with self._lock:
            manager = self._instances.get(server_id)
        if not manager:
            return {'status': 'stopped', 'message': 'Server is not running'}
        return manager.stop()

    def restart_server(self, server: Dict[str, object]) -> Dict[str, Dict[str, object]]:
        stop_result = self.stop_server(str(server['id']))
        if stop_result.get('status') != 'stopped':
            message = stop_result.get('message') or 'Unknown stop error'
            raise RuntimeError(
                f"Failed to stop server before restart: {message}. "
                "Verify no other Minecraft instance is using this world and try again."
            )
        start_result = self.start_server(server)
        return {'stop': stop_result, 'start': start_result}

    def resolve_mods_path(self, server: Dict[str, object]) -> Path:
        install_path = self._resolve_install_path(server)
        mods_path = install_path / 'mods'
        mods_path.mkdir(parents=True, exist_ok=True)
        return mods_path

    def get_logs(self, server_id: str, limit: int = 200) -> Dict[str, object]:
        with self._lock:
            manager = self._instances.get(server_id)
        if not manager:
            return {'stdout': [], 'stderr': [], 'running': False, 'message': 'Server is not running'}
        return manager.tail_logs(limit)

    def send_command(self, server_id: str, command: str) -> Dict[str, object]:
        with self._lock:
            manager = self._instances.get(server_id)
        if not manager:
            return {'success': False, 'message': 'Server is not running'}
        return manager.send_command(command)

    def invalidate(self, server_id: str) -> None:
        """Remove cached manager so next start uses fresh settings."""
        with self._lock:
            self._instances.pop(server_id, None)


_registry: Optional[ServerProcessRegistry] = None
_registry_lock = threading.Lock()


def get_server_process_registry() -> ServerProcessRegistry:
    """Return a singleton registry instance configured from app settings."""
    global _registry
    if _registry is not None:
        return _registry

    with _registry_lock:
        if _registry is None:
            config = get_config()
            _registry = ServerProcessRegistry(config.SERVERS_ROOT)
    return _registry
