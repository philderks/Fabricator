"""Process registry for managing per-server runtime state."""
from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from typing import Dict, Optional

from backend.core.config import get_config
from backend.server import java_manager
from backend.server.manager import ServerManager

DIR_PERMISSIONS = 0o775


def _format_uptime(seconds: int) -> str:
    """Format uptime seconds to human readable string."""
    if seconds < 60:
        return f"{seconds}s"

    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m"

    hours = minutes // 60
    remaining_minutes = minutes % 60
    if hours < 24:
        return f"{hours}h {remaining_minutes}m"

    days = hours // 24
    remaining_hours = hours % 24
    return f"{days}d {remaining_hours}h"


class ServerProcessRegistry:
    """Keeps track of ServerManager instances per server ID."""

    def _build_command(self, server: Dict[str, object]) -> list[str]:
        custom_command = server.get('command')
        if custom_command:
            if isinstance(custom_command, str):
                return ServerManager._split_command(custom_command)
            if isinstance(custom_command, list):
                return [str(part) for part in custom_command]

        memory = server.get('memory', 4)
        java_exec = self._resolve_java_exec(server)
        launch = server.get('launch')
        launch_type = launch.get('type') if isinstance(launch, dict) else None

        if launch_type == 'jar':
            jvm_args_raw = launch.get('jvm_args')
            jvm_args = list(jvm_args_raw) if jvm_args_raw is not None else []
            program_args_raw = launch.get('program_args')
            program_args = (
                ['nogui'] if program_args_raw is None else list(program_args_raw)
            )
            jar_name = str(launch.get('jar') or 'server.jar')
            return [
                java_exec,
                f'-Xms{memory}G',
                f'-Xmx{memory}G',
                *jvm_args,
                '-jar',
                jar_name,
                *program_args,
            ]

        if launch_type == 'args_file':
            args_file = launch.get('args_file')
            if not args_file:
                raise ValueError(
                    f"args_file-type launch on server {server.get('id')!r} "
                    "has no 'args_file' path — corrupted record?"
                )
            jvm_args_raw = launch.get('jvm_args')
            jvm_args = list(jvm_args_raw) if jvm_args_raw is not None else []
            program_args_raw = launch.get('program_args')
            program_args = (
                ['nogui'] if program_args_raw is None else list(program_args_raw)
            )
            return [
                java_exec,
                f'-Xms{memory}G',
                f'-Xmx{memory}G',
                *jvm_args,
                f'@{args_file}',
                *program_args,
            ]

        if launch_type is None:
            # Legacy fallback for records created before LaunchSpec landed.
            # Matches the historical hardcoded default exactly.
            return [
                java_exec,
                f'-Xms{memory}G',
                f'-Xmx{memory}G',
                '-jar',
                'server.jar',
                'nogui',
            ]

        # Unknown launch.type → installer/registry version mismatch (e.g. a
        # downgrade that loaded a Phase-2 NeoForge record on a Phase-0 build).
        # Fail loudly rather than silently boot the wrong way.
        raise ValueError(
            f"Unknown launch.type {launch_type!r} on server "
            f"{server.get('id')!r} — installer/registry version mismatch?"
        )

    def _resolve_java_exec(self, server: Dict[str, object]) -> str:
        """Resolve the JVM binary for ``server``.

        Precedence:
        1. Explicit ``javaPath`` on the server record (user override).
        2. Managed Java install matching the server's MC version.
        3. Fall back to ``'java'`` on PATH so the existing probe / missing-java
           error flow can trigger the install modal.
        """
        explicit = server.get('javaPath')
        if explicit:
            return str(explicit)
        try:
            required = java_manager.required_java_for(str(server.get('version') or ''))
            resolved = java_manager.find_compatible_java(required)
        except Exception:
            resolved = None
        return resolved or 'java'

    def __init__(self, base_dir: str | Path):
        self.base_dir = Path(base_dir).expanduser().resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.base_dir, DIR_PERMISSIONS)
        except OSError:
            pass
        self._lock = threading.RLock()
        self._instances: Dict[str, ServerManager] = {}
        self._started_at: Dict[str, float] = {}

    def _ensure_within_root(self, candidate: Path) -> Path:
        candidate = candidate.expanduser().resolve()
        try:
            candidate.relative_to(self.base_dir)
        except ValueError as exc:  # pragma: no cover - defensive guard
            raise ValueError(
                f"Install path '{candidate}' is outside of configured server root"
            ) from exc
        candidate.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(candidate, DIR_PERMISSIONS)
        except OSError:
            pass
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
            command = self._build_command(server)
            manager = ServerManager(command=command, cwd=str(install_path))
            self._instances[server_id] = manager
            return manager

    def get_status(self, server_id: str) -> Dict[str, object]:
        server_id = str(server_id)
        with self._lock:
            manager = self._instances.get(server_id)
            started_at = self._started_at.get(server_id)
        if not manager:
            return {'status': 'stopped', 'message': 'Server process is not running'}

        status = manager.status()
        if status.get('status') == 'running' and started_at:
            uptime_seconds = max(0, int(time.time() - started_at))
            status = dict(status)
            status['uptime'] = _format_uptime(uptime_seconds)
            status['startedAt'] = started_at
        elif status.get('status') != 'running':
            with self._lock:
                self._started_at.pop(server_id, None)
        return status

    def start_server(
        self,
        server: Dict[str, object],
        required_java_major: Optional[int] = None
    ) -> Dict[str, object]:
        manager = self._get_or_create_manager(server)
        # Rebuild command so a freshly-installed managed Java is picked up
        # without requiring an explicit invalidate() between attempts.
        if not manager.is_running:
            manager.command = self._build_command(server)
        result = manager.start(required_java_major=required_java_major)
        if result.get('status') == 'running':
            server_id = str(server['id'])
            with self._lock:
                self._started_at[server_id] = time.time()
        return result

    def get_java_runtime(self, server: Dict[str, object]) -> Dict[str, object]:
        manager = self._get_or_create_manager(server)
        return manager.probe_java()

    def stop_server(self, server_id: str) -> Dict[str, object]:
        server_id = str(server_id)
        with self._lock:
            manager = self._instances.get(server_id)
            self._started_at.pop(server_id, None)
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
        time.sleep(2)
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
            self._started_at.pop(server_id, None)


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
