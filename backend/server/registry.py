"""Process registry for managing per-server runtime state."""
from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from typing import Dict, Optional

from backend.core.config import get_config
from backend.managed import ManagedConfigError, is_managed, managed_memory_gb
from backend.server import java_manager
from backend.server.jvm_args import parse_jvm_args
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
        if is_managed():
            # C3 memory pin (fail-closed): refuse to build without a valid heap.
            gb = managed_memory_gb()
            if gb is None:
                raise ManagedConfigError(
                    "managed mode is on but FABRICATOR_MANAGED_MEMORY_GB is unset "
                    "or not a positive integer; refusing to start"
                )
            # Pin the heap and drop record-supplied launch overrides at the
            # source (command / javaPath / jvmArgs / launch.jvm_args). Operate on
            # a shallow copy so the persisted record is never mutated; the
            # assembly below then runs unchanged and lands the pin in its normal
            # slot.
            server = {
                key: value
                for key, value in server.items()
                if key not in ('command', 'javaPath', 'jvmArgs')
            }
            server['memory'] = gb
            server['memoryUnit'] = 'GB'
            launch = server.get('launch')
            if isinstance(launch, dict):
                server['launch'] = {
                    key: value for key, value in launch.items() if key != 'jvm_args'
                }

        custom_command = server.get('command')
        if custom_command:
            if isinstance(custom_command, str):
                return ServerManager._split_command(custom_command)
            if isinstance(custom_command, list):
                return [str(part) for part in custom_command]

        memory = server.get('memory', 4)
        # memoryUnit selects the JVM heap suffix: 'MB' -> M, anything else
        # (default/legacy records without the field) -> G. The value itself is
        # taken verbatim, so 1536 + MB yields -Xmx1536M.
        mem_suffix = 'M' if str(server.get('memoryUnit', 'GB')).upper() == 'MB' else 'G'
        xms = f'-Xms{memory}{mem_suffix}'
        xmx = f'-Xmx{memory}{mem_suffix}'
        java_exec = self._resolve_java_exec(server)
        launch = server.get('launch')
        launch_type = launch.get('type') if isinstance(launch, dict) else None

        # User-tuned flags, appended AFTER the installer's own jvm_args in every
        # branch below: the JVM takes the last occurrence of a repeated option,
        # so this is what lets a user override an installer default rather than
        # be overridden by it. Parsed leniently — this method also runs on the
        # server-detail probe path, where raising would turn a page load into a
        # 500 (the settings route validates on write instead).
        user_jvm_args = parse_jvm_args(server.get('jvmArgs'), server.get('id'))

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
                xms,
                xmx,
                *jvm_args,
                *user_jvm_args,
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
                xms,
                xmx,
                *jvm_args,
                *user_jvm_args,
                f'@{args_file}',
                *program_args,
            ]

        if launch_type is None:
            # Legacy fallback for records created before LaunchSpec landed.
            # Matches the historical hardcoded default exactly, plus the user's
            # own flags — those are record-level, not LaunchSpec-level, so they
            # apply to legacy records too.
            return [
                java_exec,
                xms,
                xmx,
                *user_jvm_args,
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

    def resolve_install_path(self, server: Dict[str, object]) -> Path:
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

            install_path = self.resolve_install_path(server)
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
        try:
            manager = self._get_or_create_manager(server)
            # Rebuild command so a freshly-installed managed Java is picked up
            # without requiring an explicit invalidate() between attempts.
            if not manager.is_running:
                manager.command = self._build_command(server)
        except ManagedConfigError as exc:
            # Fail-closed: map the launch-builder refusal to the clean stopped
            # shape (no 500). Boot autostart logs this via _start_one and moves on.
            return {"status": "stopped", "message": str(exc)}
        result = manager.start(required_java_major=required_java_major)
        if result.get('status') == 'running':
            server_id = str(server['id'])
            with self._lock:
                self._started_at[server_id] = time.time()
        return result

    def get_java_runtime(self, server: Dict[str, object]) -> Dict[str, object]:
        manager = self._get_or_create_manager(server)
        # Same rebuild as start_server above: the guard probe must see a
        # freshly-installed managed Java exactly like the launch path does —
        # guard truth and launch truth are the same command field.
        if not manager.is_running:
            manager.command = self._build_command(server)
        return manager.probe_java()

    def stop_server(self, server_id: str) -> Dict[str, object]:
        server_id = str(server_id)
        with self._lock:
            manager = self._instances.get(server_id)
            self._started_at.pop(server_id, None)
        if not manager:
            return {'status': 'stopped', 'message': 'Server is not running'}
        return manager.stop()

    def stop_all_running(self, timeout: float = 45.0) -> Dict[str, str]:
        """Gracefully stop every running server in parallel.

        Spawns one thread per running manager so total wall-clock stays ~a
        single server's stop time (``ServerManager.stop`` waits up to 30s for a
        clean ``stop``-command save) regardless of how many are running, then
        joins on a shared deadline. Drives the signal-based shutdown path so
        ``docker stop`` / Ctrl-C / tray-quit save worlds instead of getting the
        JVM children SIGKILLed. ``timeout`` must stay below the container's
        ``stop_grace_period`` (60s) so the join finishes before Docker escalates
        to SIGKILL. Returns a ``{server_id: status}`` map for what it attempted.
        """
        with self._lock:
            targets = [
                (server_id, manager)
                for server_id, manager in self._instances.items()
                if manager.is_running
            ]
        if not targets:
            return {}

        results: Dict[str, str] = {}
        results_lock = threading.Lock()

        def _stop_one(server_id: str, manager: ServerManager) -> None:
            # Each manager guards itself with its own lock, so concurrent stops
            # of distinct servers never collide.
            try:
                outcome = manager.stop()
                status = str(outcome.get('status', 'unknown'))
            except Exception as exc:  # one server must not block the others
                status = f'error: {exc}'
            with results_lock:
                results[server_id] = status
            with self._lock:
                self._started_at.pop(server_id, None)

        threads = [
            threading.Thread(
                target=_stop_one,
                args=(server_id, manager),
                name=f'shutdown-stop-{server_id}',
                daemon=True,
            )
            for server_id, manager in targets
        ]
        for thread in threads:
            thread.start()

        deadline = time.time() + timeout
        for thread in threads:
            thread.join(max(0.0, deadline - time.time()))
        return results

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

    def resolve_content_path(self, server: Dict[str, object]) -> Path:
        """Resolve the per-server add-on content folder.

        Bukkit-family loaders (Paper/Purpur/Folia/Pufferfish) keep their
        add-ons in ``plugins/``; mod loaders (and the legacy default) use
        ``mods/``. The distinction comes from the installer's ``content_kind``
        so the loader registry stays the single source of truth. Creates the
        folder if missing and returns its path.
        """
        from backend.server.installer import loader_content_kind

        install_path = self.resolve_install_path(server)
        loader = str(server.get('loader') or '').strip().lower()
        kind = loader_content_kind(loader)
        folder = 'plugins' if kind == 'plugin' else 'mods'
        content_path = install_path / folder
        content_path.mkdir(parents=True, exist_ok=True)
        return content_path

    def resolve_mods_path(self, server: Dict[str, object]) -> Path:
        """Back-compat alias for :meth:`resolve_content_path`.

        Retained because many call sites (mods list/delete, install, overview
        stats) reference ``resolve_mods_path``; it now returns ``plugins/`` for
        plugin-kind loaders too.
        """
        return self.resolve_content_path(server)

    def get_logs(self, server_id: str, limit: int = 200) -> Dict[str, object]:
        with self._lock:
            manager = self._instances.get(server_id)
        if not manager:
            return {'stdout': [], 'stderr': [], 'running': False, 'message': 'Server is not running'}
        return manager.tail_logs(limit)

    def get_manager(self, server_id: str) -> Optional[ServerManager]:
        """Return the live ServerManager for ``server_id``, or None."""
        with self._lock:
            return self._instances.get(str(server_id))

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


def reset_for_tests() -> None:
    """Reset the singleton registry — for test isolation only.

    Tests that build a fresh ``create_app()`` need a clean registry so the
    new ``Config.SERVERS_ROOT`` takes effect. Production code must never
    call this; the module-global ``_registry`` stays private.
    """
    global _registry
    with _registry_lock:
        _registry = None
