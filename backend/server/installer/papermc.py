"""PaperMC-family installers (Paper, Folia) using the PaperMC Fill v3 API.

Both Paper and Folia are served by the same Fill v3 API at
``https://fill.papermc.io/v3/projects/<project>``; the only difference is the
project slug. (The legacy ``api.papermc.io/v2`` API is deprecated — it now
returns ``410 Gone``.) They distribute a prebuilt server jar per (MC version,
build), so this is a Strategy-A installer (download + hash-verify a jar)
modelled on ``vanilla.py``. Every Fill build publishes a SHA-256 for its
artefact, which we verify via ``download_with_hash_verify(sha256=...)``.

Boot: ``java -Xms<m>G -Xmx<m>G -jar server.jar nogui`` — the standard
``LaunchSpec(type="jar")`` path, so no registry/manager changes are needed.

Add-on content: both run Bukkit/Spigot plugins out of ``plugins/`` — Paper
accepts spigot/bukkit plugins, Folia requires region-thread-safe plugins so it
sticks to the strict ``folia`` facet.
"""
from __future__ import annotations

import logging
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
    validate_version_token,
)


logger = logging.getLogger(__name__)

# The Fill v3 build "download" key for the runnable server jar.
_SERVER_DOWNLOAD_KEY = "server:default"


class PaperMCInstaller(InstallerBase):
    """Shared installer for PaperMC-hosted projects (Paper, Folia).

    Subclasses set :attr:`PROJECT` to the API project slug and override
    :meth:`loader_name` / plugin-facet properties as needed.
    """

    API_BASE = "https://fill.papermc.io/v3/projects"
    #: PaperMC project slug — subclasses override.
    PROJECT: str = ""

    def __init__(self, install_path: Path):
        super().__init__(install_path)
        if not self.PROJECT:
            raise ValueError(
                f"{type(self).__name__} must set a PROJECT slug"
            )

    content_kind = "plugin"

    # ---------- API helpers ----------

    def _project_url(self, *parts: str) -> str:
        return "/".join((self.API_BASE, self.PROJECT, *parts))

    # ---------- Version listing ----------

    def get_minecraft_versions(self) -> List[Dict[str, Any]]:
        """Minecraft versions this project publishes, newest first.

        Fill v3 returns ``versions`` as a ``{family: [full_version, ...]}`` map
        with the newest family first and the newest version first within each
        family, so flattening in iteration order yields a newest-first list.
        Prerelease/experimental versions (``-rc``/``-pre`` suffixes, non-numeric
        families) are surfaced but marked ``stable=False``.
        """
        try:
            payload = self._get_json(self._project_url())
        except requests.RequestException as exc:
            logger.warning("Failed to fetch %s versions: %s", self.PROJECT, exc)
            return []

        families = payload.get("versions") or {}
        # dict.fromkeys dedupes while keeping first-seen order: the same version
        # can be listed under two families, and the UI must not offer it twice.
        return self._mc_version_entries(dict.fromkeys(
            v for version_list in families.values() for v in (version_list or [])
        ))

    def _select_build(self, mc_version: str) -> Optional[Dict[str, Any]]:
        """Return the newest ``STABLE``-channel build dict for ``mc_version``.

        Falls back to the newest build of any channel if no STABLE build exists
        (fresh snapshots ship only as ALPHA/BETA). Returns ``None`` if the
        version has no builds. Fill returns a list of build objects, each with
        an ``id`` and ``channel``.
        """
        try:
            builds = self._get_json(
                self._project_url("versions", mc_version, "builds")
            )
        except requests.RequestException as exc:
            logger.warning(
                "Failed to fetch %s builds for %s: %s",
                self.PROJECT, mc_version, exc,
            )
            return None

        if not isinstance(builds, list) or not builds:
            return None

        stable_builds = [
            b for b in builds if str(b.get("channel", "")).upper() == "STABLE"
        ]
        pool = stable_builds or builds
        return max(pool, key=lambda b: b.get("id", 0))

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

        # mc_version arrives from user JSON — whitelist before it lands in a URL
        # path segment.
        try:
            mc_version = validate_version_token(mc_version, field_name="mc_version")
        except ValueError as exc:
            msg = str(exc)
            return self._fail(progress_callback, msg, mc_version=mc_version)

        self._report(progress_callback, "resolving_versions")
        build = self._select_build(mc_version)
        if not build:
            msg = (
                f"No {self.PROJECT.capitalize()} build found for "
                f"Minecraft {mc_version}."
            )
            return self._fail(progress_callback, msg, mc_version=mc_version)

        build_number = build.get("id")
        download = (build.get("downloads") or {}).get(_SERVER_DOWNLOAD_KEY) or {}
        download_url = download.get("url")
        expected_sha256 = (download.get("checksums") or {}).get("sha256")
        if not download_url:
            msg = (
                f"{self.PROJECT.capitalize()} build {build_number} for "
                f"{mc_version} has no downloadable server artefact."
            )
            return self._fail(
                progress_callback,
                msg,
                mc_version=mc_version,
                build=build_number,
            )

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
                "Downloading %s %s build %s from %s",
                self.PROJECT, mc_version, build_number, download_url,
            )
            download_with_hash_verify(
                download_url,
                jar_path,
                sha256=expected_sha256,
                session=self.session,
                timeout=300,
                progress_callback=_emit,
                retries=3,
            )
        except HashVerifyError as exc:
            msg = f"{self.PROJECT.capitalize()} server jar failed integrity check: {exc}"
            return self._fail(
                progress_callback,
                msg,
                mc_version=mc_version,
                build=build_number,
            )
        except requests.RequestException as exc:
            msg = f"Failed to download {self.PROJECT.capitalize()} server jar: {exc}"
            return self._fail(
                progress_callback,
                msg,
                mc_version=mc_version,
                build=build_number,
            )
        except OSError as exc:
            msg = f"Failed to write {self.PROJECT.capitalize()} server jar: {exc}"
            return self._fail(
                progress_callback,
                msg,
                mc_version=mc_version,
                build=build_number,
            )

        if not jar_path.exists():
            msg = f"Failed to download {self.PROJECT.capitalize()} server jar"
            return self._fail(
                progress_callback,
                msg,
                mc_version=mc_version,
                build=build_number,
            )

        self._report(progress_callback, "writing_eula")
        self._write_eula(accepted=True)

        self._report(progress_callback, "done")
        return InstallResult(
            success=True,
            status=InstallStatus.COMPLETED,
            message=(
                f"{self.PROJECT.capitalize()} {mc_version} "
                f"(build {build_number}) installed successfully"
            ),
            server_jar=jar_path,
            details={
                "mc_version": mc_version,
                "build": build_number,
                "jar_file": str(jar_path),
                "install_path": str(self.install_path),
                "sha256": expected_sha256,
            },
            launch=LaunchSpec(
                type="jar",
                jar="server.jar",
                jvm_args=[],
                program_args=["nogui"],
            ),
        )


class PaperInstaller(PaperMCInstaller):
    """Paper — the most popular Bukkit-family server (Spigot superset)."""

    PROJECT = "paper"

    @property
    def loader_name(self) -> str:
        return "paper"

    @property
    def modrinth_loader_facets(self) -> List[str]:
        # Paper runs Paper-, Spigot-, and Bukkit-targeted plugins.
        return ["paper", "spigot", "bukkit"]


class FoliaInstaller(PaperMCInstaller):
    """Folia — Paper's regionised-multithreading fork."""

    PROJECT = "folia"

    @property
    def loader_name(self) -> str:
        return "folia"

    @property
    def modrinth_loader_facets(self) -> List[str]:
        # Folia needs region-thread-safe plugins; do NOT silently accept
        # generic Paper/Spigot plugins that may not be Folia-aware.
        return ["folia"]
