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
# Loaders whose build can be swapped under an unchanged Minecraft version (#104).
_LOADER_BUILD_LOADERS = frozenset({"fabric", "quilt", "forge", "neoforge"})

# A numbered stable release, in either naming scheme Mojang has shipped: the
# classic ``1.y`` / ``1.y.z`` era and the year-based ``26.n`` / ``26.n.p`` one.
# Anything carrying a suffix (``1.21-rc1``, ``26.2-snapshot-6``), a weekly
# snapshot name (``24w14a``), or a legacy alpha/beta name (``b1.7.3``) is
# deliberately excluded — see :func:`_release_version_key`.
_RELEASE_VERSION_RE = re.compile(r"^(\d+)\.(\d+)(?:\.(\d+))?$")
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


def _release_version_key(version: object) -> tuple[int, int, int]:
    """Convert a stable Minecraft release into a comparable tuple.

    The key is the full ``(major, minor, patch)`` triple rather than just the
    ``1.y.z`` tail, so the two naming schemes order against each other for
    free: every year-based release (``26.2`` -> ``(26, 2, 0)``) sorts above
    every ``1.x`` release (``1.21.4`` -> ``(1, 21, 4)``), which is exactly the
    real release order. An omitted patch is ``.0`` — Mojang writes ``1.21``
    and ``26.2`` for what are internally ``1.21.0`` / ``26.2.0``.

    Snapshots, release candidates, and non-release legacy version names are
    intentionally unsupported. They require semantics beyond the safe one-way
    release-to-release migration offered here.
    """
    value = str(version or "").strip()
    match = _RELEASE_VERSION_RE.fullmatch(value)
    if not match:
        raise UpgradeError(
            "Upgrades currently require numbered Minecraft releases "
            "such as 1.20.1, 1.21, or 26.3. Snapshots and pre-releases "
            "are not supported."
        )
    return int(match.group(1)), int(match.group(2)), int(match.group(3) or 0)


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


def loader_build_available(installer: Any, mc_version: str, build: str) -> bool:
    """Whether ``installer`` can supply loader ``build`` for ``mc_version``.

    Raises whatever the installer's version listing raises; callers decide
    whether an unreadable list is fatal.
    """
    known = {
        str(v.get("version") if isinstance(v, dict) else v).strip()
        for v in (installer.get_available_versions(mc_version) or [])
    }
    return str(build or "").strip() in known


def validate_loader_upgrade(server: Dict[str, Any], build: object) -> str:
    """Validate a request to swap the loader build of a modded server."""
    loader = str(server.get("loader") or "").strip().lower()
    if loader not in _LOADER_BUILD_LOADERS:
        raise UpgradeError(
            "Changing the loader build is only supported for Fabric, Quilt, "
            "Forge and NeoForge servers."
        )
    target = str(build or "").strip()
    if not target:
        raise UpgradeError("No loader version given")
    mc_version = str(server.get("version") or "").strip()
    # Only lists versions, so the install path is never touched.
    installer = get_installer_for(loader, Path("."))
    try:
        available = loader_build_available(installer, mc_version, target)
    except Exception as exc:  # noqa: BLE001 - network/metadata failure
        raise UpgradeError(f"Could not list {loader} versions: {exc}") from exc
    if not available:
        raise UpgradeError(
            f"{loader} {target} is not available for Minecraft {mc_version}"
        )
    return target


def upgrade_loader(
    server_id: str,
    build: object,
    *,
    progress_callback: Optional[ProgressCallback] = None,
) -> Dict[str, Any]:
    """Back up, stop, install loader ``build`` for the same Minecraft version.

    Mirrors :func:`upgrade_server`. A modpack update can pin a different
    loader build than the server runs, and its mods are compiled against that
    build (see ``_pack_loader_version`` in routes), so the pack switch alone
    is not enough (#104).
    """
    lock = get_server_lock(server_id)
    with lock:
        server = server_storage.get_server(server_id)
        if not server:
            raise UpgradeError("Server not found")
        target = validate_loader_upgrade(server, build)
        mc_version = str(server["version"])
        previous_build = server.get("loaderVersion")

        registry = get_server_process_registry()
        install_path = registry.resolve_install_path(server)
        installer = get_installer_for(str(server["loader"]), install_path)
        if installer is None:  # defensive; validate_loader_upgrade already gates it
            raise UpgradeError("No installer is available for this server")

        runtime = registry.get_java_runtime(server)
        if installer.requires_java_for_install and runtime.get("java_missing"):
            raise UpgradeError("Java is required to install this loader")
        installer.set_java_exec(runtime.get("java_exec"))

        if progress_callback:
            progress_callback("creating_backup", {"from_version": previous_build})
        snapshot = backup_service.run_adhoc_backup(
            server_id,
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
            # Not install_with_config: it would overwrite user-edited
            # server.properties. A failed install leaves the old launch record
            # in place, whose loader files the installer does not remove.
            result = installer.install(
                mc_version, target, progress_callback=_installer_progress
            )
            if not result.success:
                raise UpgradeError(result.message)

            updates: Dict[str, Any] = {"loaderVersion": target, "status": "stopped"}
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
            "from_loader_version": previous_build,
            "to_loader_version": target,
            "snapshot_id": snapshot.get("id"),
        }
