"""Safe, first-stage Minecraft server upgrades.

This stage supports the jar-only server types whose upgrade layout is stable:
Vanilla and Paper. It deliberately refuses modded loaders. An upgrade always
creates an ad-hoc full-server snapshot before stopping the server or replacing
``server.jar``; restoring that snapshot is the recovery path if Minecraft's
world migration is not acceptable.
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from backend.backups import service as backup_service
from backend.server import storage as server_storage
from backend.server.installer import get_installer_for
from backend.server.locks import get_server_lock
from backend.server.registry import get_server_process_registry

_SUPPORTED_LOADERS = frozenset({"vanilla", "paper"})
_RELEASE_VERSION_RE = re.compile(r"^1\.(\d+)(?:\.(\d+))?$")
ProgressCallback = Callable[[str, Dict[str, Any]], None]


class UpgradeError(ValueError):
    """A request that cannot safely be performed as a stage-one upgrade."""


def _preserve_server_jar(install_path: Path) -> Path | None:
    """Copy the runnable jar aside before an installer touches its destination.

    Both stage-one installers download straight to ``server.jar`` and remove a
    failed target download. Keeping this small local rollback copy means a
    transient download/integrity failure never turns a working server into an
    unstartable one while the full snapshot remains the wider recovery option.
    """
    original = install_path / "server.jar"
    if not original.is_file():
        return None
    rollback = install_path / ".fabricator-server.jar.before-upgrade"
    try:
        shutil.copy2(original, rollback)
    except OSError as exc:
        raise UpgradeError(f"Could not preserve the current server.jar: {exc}") from exc
    return rollback


def _restore_server_jar(rollback: Path | None, install_path: Path) -> None:
    if rollback is None:
        return
    try:
        shutil.copy2(rollback, install_path / "server.jar")
    except OSError as exc:
        raise UpgradeError(
            f"Upgrade failed and Fabricator could not restore the previous server.jar: {exc}"
        ) from exc


def _discard_rollback_jar(rollback: Path | None) -> None:
    if rollback is None:
        return
    try:
        rollback.unlink(missing_ok=True)
    except OSError:
        pass


def _release_version_key(version: object) -> tuple[int, int]:
    """Convert a stable Minecraft release into a comparable tuple.

    Snapshots, release candidates, and non-release legacy version names are
    intentionally unsupported in the first release. They require semantics
    beyond the safe one-way release-to-release migration offered here.
    """
    value = str(version or "").strip()
    match = _RELEASE_VERSION_RE.fullmatch(value)
    if not match:
        raise UpgradeError(
            "Upgrades currently require stable Minecraft release versions "
            "such as 1.20.1 or 1.21."
        )
    return int(match.group(1)), int(match.group(2) or 0)


def validate_upgrade(server: Dict[str, Any], target_version: object) -> str:
    """Validate the non-destructive prerequisites for an upgrade request."""
    loader = str(server.get("loader") or "").strip().lower()
    if loader not in _SUPPORTED_LOADERS:
        raise UpgradeError(
            "The first upgrade stage only supports vanilla and Paper servers."
        )

    current_version = str(server.get("version") or "").strip()
    target = str(target_version or "").strip()
    current_key = _release_version_key(current_version)
    target_key = _release_version_key(target)
    if target_key <= current_key:
        raise UpgradeError(
            f"Target Minecraft version must be newer than the current "
            f"version ({current_version}). Downgrades are not supported."
        )
    return target


def upgrade_server(
    server_id: str,
    target_version: object,
    *,
    progress_callback: Optional[ProgressCallback] = None,
) -> Dict[str, Any]:
    """Back up, stop, replace the server jar, then persist the new version.

    The function is synchronous so an async route can own the worker lifecycle.
    It holds the existing per-server RLock across the complete operation; the
    nested backup call is safe because the lock is re-entrant in this thread.
    """
    server = server_storage.get_server(server_id)
    if not server:
        raise UpgradeError("Server not found")
    target = validate_upgrade(server, target_version)
    previous_version = str(server["version"])

    lock = get_server_lock(server_id)
    with lock:
        # Re-read after acquiring the lock so a settings edit cannot change the
        # loader/version between request validation and the destructive phase.
        server = server_storage.get_server(server_id)
        if not server:
            raise UpgradeError("Server not found")
        target = validate_upgrade(server, target)
        previous_version = str(server["version"])

        registry = get_server_process_registry()
        install_path = registry.resolve_install_path(server)
        installer = get_installer_for(str(server["loader"]), install_path)
        if installer is None:  # defensive; validate_upgrade already gates it
            raise UpgradeError("No installer is available for this server")

        if progress_callback:
            progress_callback("creating_backup", {"from_version": previous_version})
        snapshot = backup_service.run_adhoc_backup(
            server_id,
            # An upgrade snapshot must capture the whole server directory. The
            # default location stays inside it, where backup service avoids
            # recursively archiving its own output.
            compress=True,
            flush=True,
            shutdown=False,
            trigger="upgrade",
        )

        if progress_callback:
            progress_callback("stopping_server", {})
        registry.stop_server(server_id)
        rollback_jar = _preserve_server_jar(install_path)

        def _installer_progress(phase: str, detail: Dict[str, Any]) -> None:
            if progress_callback:
                progress_callback(phase, detail)

        try:
            # Do not call install_with_config: it regenerates server.properties
            # and would overwrite user-edited settings. Vanilla/Paper install()
            # only replaces server.jar and refreshes the EULA.
            result = installer.install(target, progress_callback=_installer_progress)
            if not result.success:
                raise UpgradeError(result.message)

            updates: Dict[str, Any] = {"version": target, "status": "stopped"}
            if result.launch is not None:
                updates["launch"] = result.launch.to_dict()
            server_storage.update_server(server_id, updates)
        except Exception:
            _restore_server_jar(rollback_jar, install_path)
            raise
        else:
            _discard_rollback_jar(rollback_jar)

        if progress_callback:
            progress_callback("done", {"snapshot_id": snapshot.get("id")})
        return {
            "server_id": server_id,
            "from_version": previous_version,
            "to_version": target,
            "snapshot_id": snapshot.get("id"),
        }
