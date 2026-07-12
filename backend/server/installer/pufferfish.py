"""Pufferfish server installer using the Pufferfish Jenkins CI.

Pufferfish is a highly-optimised Paper fork. Unlike Paper/Purpur it has **no
stable REST download API** — it publishes only through Jenkins at
``https://ci.pufferfish.host``. Each supported Minecraft minor line has its own
job named ``Pufferfish-<version>`` (e.g. ``Pufferfish-1.21``) whose
``lastSuccessfulBuild`` carries the server jar under ``build/libs/``.

This is therefore the **most fragile** integration here: if Pufferfish changes
its job-naming or artefact layout, resolution fails. We isolate all URL logic
in this module and fail with a clear message rather than guessing, so a CI
change surfaces as an actionable error instead of a corrupt install.

Integrity: Jenkins publishes no hash for the artefact, so we download via the
Content-Length size-check path (same precedent as Fabric's hash-less jar).

Boot: standard ``LaunchSpec(type="jar", jar="server.jar")``. Plugins live in
``plugins/`` — Pufferfish runs Paper/Spigot/Bukkit plugins.
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

# Matches the vanilla-Pufferfish jobs (``Pufferfish-1.21``) and captures the MC
# version. Deliberately requires a digit after the dash so the separate
# ``Pufferfish-Purpur-1.17`` (a Purpur-based variant) jobs are excluded.
_JOB_RE = re.compile(r"^Pufferfish-(\d[\w.]*)$")


class PufferfishInstaller(InstallerBase):
    """Installer for Pufferfish servers (Jenkins-hosted)."""

    CI_BASE = "https://ci.pufferfish.host"
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
        return "pufferfish"

    content_kind = "plugin"

    @property
    def modrinth_loader_facets(self) -> List[str]:
        # No dedicated Modrinth "pufferfish" category — it runs Paper plugins.
        return ["paper", "spigot", "bukkit"]

    # ---------- CI helpers ----------

    def _get_json(self, url: str) -> Dict[str, Any]:
        def _do_request() -> Dict[str, Any]:
            response = self.session.get(url, timeout=15)
            response.raise_for_status()
            return response.json()

        return request_with_retry(
            _do_request,
            retries=3,
            on_retry=lambda attempt, exc: logger.warning(
                "Retrying Pufferfish CI fetch %s (attempt %d): %s",
                url, attempt, exc,
            ),
        )

    def _fetch_jobs(self) -> List[Dict[str, Any]]:
        """Return the Jenkins job list (``[{"name": ...}, ...]``)."""
        payload = self._get_json(
            f"{self.CI_BASE}/api/json?tree=jobs[name]"
        )
        return payload.get("jobs") or []

    # ---------- Version listing ----------

    def get_minecraft_versions(self) -> List[Dict[str, Any]]:
        """Minecraft minor lines Pufferfish builds, newest first.

        Derived from the ``Pufferfish-<version>`` Jenkins jobs. These are minor
        lines (e.g. ``1.21``) that track the latest patch, not full patch
        versions. Newest-first by numeric sort.
        """
        try:
            jobs = self._fetch_jobs()
        except requests.RequestException as exc:
            logger.warning("Failed to fetch Pufferfish CI jobs: %s", exc)
            return []

        versions: List[str] = []
        for job in jobs:
            match = _JOB_RE.match(str(job.get("name") or ""))
            if match:
                versions.append(match.group(1))

        versions.sort(key=self._mc_version_sort_key, reverse=True)
        return [
            {
                "version": self._canonicalize_mc_version(v),
                "stable": True,
                "type": "release",
            }
            for v in versions
        ]

    def get_available_versions(
        self, mc_version: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        return []

    def _resolve_job_name(self, mc_version: str) -> Optional[str]:
        """Return the exact Jenkins job name for ``mc_version`` if it exists.

        We build the expected ``Pufferfish-<mc_version>`` name but confirm it
        against the live job list so a naming change surfaces as "no build
        found" rather than a 404 mid-download.
        """
        expected = f"Pufferfish-{mc_version}"
        try:
            jobs = self._fetch_jobs()
        except requests.RequestException as exc:
            logger.warning("Failed to fetch Pufferfish CI jobs: %s", exc)
            return None
        for job in jobs:
            if str(job.get("name") or "") == expected:
                return expected
        return None

    def _resolve_artifact_path(self, job_name: str) -> Optional[str]:
        """Return the server-jar artefact relativePath for a job.

        Reads ``lastSuccessfulBuild`` and picks the runnable jar under a
        ``build/libs/`` directory (the real path is nested, e.g.
        ``pufferfish-server/build/libs/pufferfish-paperclip-<mc>-...jar``),
        skipping ``-sources``/``-javadoc`` classifier jars. Returns ``None`` if
        the layout doesn't match expectations.

        Selection is deterministic when a build publishes more than one
        candidate jar: the ``paperclip`` bootstrap jar (the one you actually
        run) is preferred, then ``mojmap`` mappings, otherwise the first
        candidate in listing order. Without this a multi-artefact build could
        arbitrarily pick a non-runnable bundler/reobf jar.
        """
        url = (
            f"{self.CI_BASE}/job/{job_name}/lastSuccessfulBuild/"
            "api/json?tree=artifacts[fileName,relativePath]"
        )
        try:
            payload = self._get_json(url)
        except requests.RequestException as exc:
            logger.warning(
                "Failed to fetch Pufferfish artefacts for %s: %s", job_name, exc
            )
            return None

        candidates: List[str] = []
        for artifact in payload.get("artifacts") or []:
            rel = str(artifact.get("relativePath") or "")
            name = str(artifact.get("fileName") or "")
            if "build/libs/" not in rel or not rel.endswith(".jar"):
                continue
            if "-sources" in name or "-javadoc" in name:
                continue
            candidates.append(rel)

        if not candidates:
            return None

        def _score(rel: str) -> int:
            lower = rel.lower()
            score = 0
            if "paperclip" in lower:
                score += 2
            if "mojmap" in lower:
                score += 1
            return score

        # max() keeps the first candidate on a score tie, preserving listing
        # order as the stable fallback.
        return max(candidates, key=_score)

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
        job_name = self._resolve_job_name(mc_version)
        if not job_name:
            msg = (
                f"No Pufferfish build found for Minecraft {mc_version}. "
                "Pufferfish only publishes selected minor versions on its CI."
            )
            self._report(progress_callback, "failed", error=msg)
            return InstallResult(
                success=False,
                status=InstallStatus.FAILED,
                message=msg,
                details={"mc_version": mc_version},
            )

        artifact_rel = self._resolve_artifact_path(job_name)
        if not artifact_rel:
            msg = (
                "Pufferfish CI did not expose a server jar under build/libs "
                f"for {mc_version}. The CI layout may have changed."
            )
            self._report(progress_callback, "failed", error=msg)
            return InstallResult(
                success=False,
                status=InstallStatus.FAILED,
                message=msg,
                details={"mc_version": mc_version, "job": job_name},
            )

        download_url = (
            f"{self.CI_BASE}/job/{job_name}/lastSuccessfulBuild/"
            f"artifact/{artifact_rel}"
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
                "Downloading Pufferfish %s from %s", mc_version, download_url
            )
            # No CI-published hash → size-check path.
            download_with_hash_verify(
                download_url,
                jar_path,
                session=self.session,
                timeout=300,
                progress_callback=_emit,
                retries=3,
            )
        except HashVerifyError as exc:
            msg = f"Pufferfish server jar failed size check: {exc}"
            self._report(progress_callback, "failed", error=msg)
            return InstallResult(
                success=False,
                status=InstallStatus.FAILED,
                message=msg,
                details={"mc_version": mc_version, "job": job_name},
            )
        except requests.RequestException as exc:
            msg = f"Failed to download Pufferfish server jar: {exc}"
            self._report(progress_callback, "failed", error=msg)
            return InstallResult(
                success=False,
                status=InstallStatus.FAILED,
                message=msg,
                details={"mc_version": mc_version, "job": job_name},
            )
        except OSError as exc:
            msg = f"Failed to write Pufferfish server jar: {exc}"
            self._report(progress_callback, "failed", error=msg)
            return InstallResult(
                success=False,
                status=InstallStatus.FAILED,
                message=msg,
                details={"mc_version": mc_version, "job": job_name},
            )

        if not jar_path.exists():
            msg = "Failed to download Pufferfish server jar"
            self._report(progress_callback, "failed", error=msg)
            return InstallResult(
                success=False,
                status=InstallStatus.FAILED,
                message=msg,
                details={"mc_version": mc_version, "job": job_name},
            )

        self._report(progress_callback, "writing_eula")
        self._write_eula(accepted=True)

        self._report(progress_callback, "done")
        return InstallResult(
            success=True,
            status=InstallStatus.COMPLETED,
            message=f"Pufferfish {mc_version} installed successfully",
            server_jar=jar_path,
            details={
                "mc_version": mc_version,
                "job": job_name,
                "artifact": artifact_rel,
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
