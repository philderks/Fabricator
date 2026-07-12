"""Purpur server installer using the Purpur v2 API.

Purpur is a Paper fork with extra config knobs. It distributes a prebuilt
server jar per (MC version, build) via ``https://api.purpurmc.org/v2/purpur``,
so this is a Strategy-A installer modelled on ``vanilla.py`` / ``papermc.py``.

Integrity note: Purpur's API publishes only an MD5 for its builds (not a
SHA-1/256/512). MD5 is too weak to be a meaningful tamper gate, so we download
via the no-hash / Content-Length size-check path (the same precedent as
Fabric Meta's hash-less server jar). ``download_with_hash_verify`` still
streams atomically and cleans up partial files on failure.

Boot: standard ``LaunchSpec(type="jar", jar="server.jar")``. Plugins live in
``plugins/`` — Purpur runs Purpur/Paper/Spigot/Bukkit plugins.
"""
from __future__ import annotations

import logging
import re
import requests
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .base import (
    HashVerifyError,
    InstallerBase,
    InstallResult,
    InstallStatus,
    LaunchSpec,
    download_with_hash_verify,
    request_with_retry,
    validate_version_token,
)


logger = logging.getLogger(__name__)

# Mainstream Minecraft releases are ``1.x`` — Purpur also lists experimental
# families (e.g. ``26.2``); mark those non-stable so a new server never
# defaults to one (parity with the Paper installer's heuristic).
_STABLE_MC_RE = re.compile(r"^1\.\d+(\.\d+)?$")


class PurpurInstaller(InstallerBase):
    """Installer for Purpur servers."""

    API_BASE = "https://api.purpurmc.org/v2/purpur"
    USER_AGENT = (
        "philderks/Fabricator/1.0.0 (https://github.com/philderks/Fabricator)"
    )

    def __init__(self, install_path: Path):
        super().__init__(install_path)
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": self.USER_AGENT,
            "Accept": "application/json",
        })

    @property
    def loader_name(self) -> str:
        return "purpur"

    @property
    def content_kind(self) -> str:
        return "plugin"

    @property
    def modrinth_loader_facets(self) -> List[str]:
        return ["purpur", "paper", "spigot", "bukkit"]

    # ---------- API helpers ----------

    def _get_json(self, url: str) -> Dict[str, Any]:
        def _do_request() -> Dict[str, Any]:
            response = self.session.get(url, timeout=15)
            response.raise_for_status()
            return response.json()

        return request_with_retry(
            _do_request,
            retries=3,
            on_retry=lambda attempt, exc: logger.warning(
                "Retrying Purpur fetch %s (attempt %d): %s", url, attempt, exc,
            ),
        )

    # ---------- Version listing ----------

    def get_minecraft_versions(self) -> List[Dict[str, Any]]:
        """Minecraft versions Purpur publishes, newest first."""
        try:
            payload = self._get_json(self.API_BASE)
        except requests.RequestException as exc:
            logger.warning("Failed to fetch Purpur versions: %s", exc)
            return []

        versions = payload.get("versions") or []
        out: List[Dict[str, Any]] = []
        for v in reversed(versions):
            if not v:
                continue
            stable = bool(_STABLE_MC_RE.match(str(v)))
            out.append({
                "version": self._canonicalize_mc_version(str(v)),
                "stable": stable,
                "type": "release" if stable else "snapshot",
            })
        return out

    def get_available_versions(
        self, mc_version: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        # Build is resolved to the latest at install time; no user-picked
        # loader version to surface.
        return []

    def _select_build(self, mc_version: str) -> Optional[str]:
        """Return Purpur's latest build number for ``mc_version`` as a string.

        ``GET /purpur/<mc>`` returns ``{"builds": {"latest": "<n>", "all": [...]}}``.
        Returns ``None`` if the version is unknown or has no builds.
        """
        try:
            payload = self._get_json(f"{self.API_BASE}/{mc_version}")
        except requests.RequestException as exc:
            logger.warning(
                "Failed to fetch Purpur builds for %s: %s", mc_version, exc
            )
            return None

        builds = payload.get("builds") or {}
        latest = builds.get("latest")
        if latest is not None:
            return str(latest)
        all_builds = builds.get("all") or []
        if all_builds:
            return str(all_builds[-1])
        return None

    # ---------- Install ----------

    def install(
        self,
        mc_version: str,
        loader_version: Optional[str] = None,
        progress_callback: Optional[
            "Callable[[str, Dict[str, Any]], None]"
        ] = None,
    ) -> InstallResult:
        self._report(progress_callback, "starting")
        self._ensure_install_dir()

        try:
            mc_version = validate_version_token(mc_version, field_name="mc_version")
        except ValueError as exc:
            msg = str(exc)
            self._report(progress_callback, "failed", error=msg)
            return InstallResult(
                success=False,
                status=InstallStatus.FAILED,
                message=msg,
                details={"mc_version": mc_version},
            )

        self._report(progress_callback, "resolving_versions")
        build = self._select_build(mc_version)
        if not build:
            msg = f"No Purpur build found for Minecraft {mc_version}."
            self._report(progress_callback, "failed", error=msg)
            return InstallResult(
                success=False,
                status=InstallStatus.FAILED,
                message=msg,
                details={"mc_version": mc_version},
            )

        try:
            build = validate_version_token(build, field_name="build")
        except ValueError as exc:
            msg = str(exc)
            self._report(progress_callback, "failed", error=msg)
            return InstallResult(
                success=False,
                status=InstallStatus.FAILED,
                message=msg,
                details={"mc_version": mc_version, "build": build},
            )

        download_url = f"{self.API_BASE}/{mc_version}/{build}/download"
        jar_path = self.install_path / "server.jar"

        def _emit(bytes_done: int, bytes_total: int) -> None:
            self._report(
                progress_callback,
                "downloading_server_jar",
                bytes_done=bytes_done,
                bytes_total=bytes_total,
            )

        try:
            logger.info(
                "Downloading Purpur %s build %s from %s",
                mc_version, build, download_url,
            )
            # Purpur publishes only MD5 (too weak to gate on); download via the
            # size-check path, same as Fabric's hash-less server jar.
            download_with_hash_verify(
                download_url,
                jar_path,
                session=self.session,
                timeout=300,
                progress_callback=_emit,
                retries=3,
            )
        except HashVerifyError as exc:
            # Only reachable via the size-check branch (Content-Length mismatch).
            msg = f"Purpur server jar failed size check: {exc}"
            self._report(progress_callback, "failed", error=msg)
            return InstallResult(
                success=False,
                status=InstallStatus.FAILED,
                message=msg,
                details={"mc_version": mc_version, "build": build},
            )
        except requests.RequestException as exc:
            msg = f"Failed to download Purpur server jar: {exc}"
            self._report(progress_callback, "failed", error=msg)
            return InstallResult(
                success=False,
                status=InstallStatus.FAILED,
                message=msg,
                details={"mc_version": mc_version, "build": build},
            )
        except OSError as exc:
            msg = f"Failed to write Purpur server jar: {exc}"
            self._report(progress_callback, "failed", error=msg)
            return InstallResult(
                success=False,
                status=InstallStatus.FAILED,
                message=msg,
                details={"mc_version": mc_version, "build": build},
            )

        if not jar_path.exists():
            msg = "Failed to download Purpur server jar"
            self._report(progress_callback, "failed", error=msg)
            return InstallResult(
                success=False,
                status=InstallStatus.FAILED,
                message=msg,
                details={"mc_version": mc_version, "build": build},
            )

        self._report(progress_callback, "writing_eula")
        self._write_eula(accepted=True)

        self._report(progress_callback, "done")
        return InstallResult(
            success=True,
            status=InstallStatus.COMPLETED,
            message=f"Purpur {mc_version} (build {build}) installed successfully",
            server_jar=jar_path,
            details={
                "mc_version": mc_version,
                "build": build,
                "jar_file": str(jar_path),
                "install_path": str(self.install_path),
            },
            launch=LaunchSpec(
                type="jar",
                jar="server.jar",
                jvm_args=[],
                program_args=["nogui"],
            ),
        )

    def install_with_config(
        self,
        mc_version: str,
        server_config: Dict[str, Any],
        loader_version: Optional[str] = None,
        progress_callback: Optional[
            "Callable[[str, Dict[str, Any]], None]"
        ] = None,
    ) -> InstallResult:
        result = self.install(
            mc_version, loader_version, progress_callback=progress_callback
        )
        if not result.success:
            return result

        properties = self.generate_server_properties(server_config)
        self._write_server_properties(properties)
        if result.details:
            result.details["server_properties"] = str(
                self.install_path / "server.properties"
            )
        return result
