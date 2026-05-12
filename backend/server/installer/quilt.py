"""Quilt server installer.

Pattern: subprocess-driven install, jar-launched runtime.

Install:
    java -jar quilt-installer-<v>.jar install server <mc_version> \
        --download-server --install-dir=<install_path>

(``--install-dir`` is required: without it the installer creates a ``server/``
subdirectory and drops everything one level deeper than we expect, making
``_detect_launch_jar`` miss the file.)

Output (in install_path):
    quilt-server-launch.jar   ← what we boot
    libraries/                ← classpath referenced by the launcher's manifest
    server.jar                ← vanilla MC server JAR

Boot (via _build_command's existing jar branch):
    java -Xms<mem>G -Xmx<mem>G -jar quilt-server-launch.jar nogui
"""
from __future__ import annotations

import re
import requests
import subprocess
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from backend.utils import platform as platform_utils

from .base import (
    InstallerBase,
    InstallResult,
    InstallStatus,
    LaunchSpec,
    validate_version_token,
)


_MAVEN_RELEASE_RE = re.compile(r"<release>([^<]+)</release>")


class QuiltInstaller(InstallerBase):
    META_BASE = "https://meta.quiltmc.org/v3"
    MAVEN_BASE = "https://maven.quiltmc.org/repository/release"
    INSTALLER_GROUP_PATH = "org/quiltmc/quilt-installer"
    USER_AGENT = (
        "philderks/Fabricator/1.0.0 (https://github.com/philderks/Fabricator)"
    )
    LAUNCH_JAR_NAME = "quilt-server-launch.jar"

    def __init__(self, install_path: Path):
        super().__init__(install_path)
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": self.USER_AGENT,
            "Accept": "application/json",
        })

    @property
    def loader_name(self) -> str:
        return "quilt"

    @property
    def requires_java_for_install(self) -> bool:
        return True

    # ---------- Version listing ----------

    def get_minecraft_versions(self) -> List[Dict[str, Any]]:
        try:
            response = self.session.get(
                f"{self.META_BASE}/versions/game", timeout=15
            )
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as exc:
            print(f"Failed to fetch Quilt game versions: {exc}")
            return []

        out: List[Dict[str, Any]] = []
        for entry in payload:
            version = entry.get("version")
            if not version:
                continue
            stable = bool(entry.get("stable"))
            out.append({
                "version": self._canonicalize_mc_version(version),
                "stable": stable,
                "type": "release" if stable else "snapshot",
            })
        return out

    def get_available_versions(
        self, mc_version: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        if not mc_version:
            return []
        try:
            response = self.session.get(
                f"{self.META_BASE}/versions/loader/{mc_version}", timeout=15
            )
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException:
            # 404 for unsupported MC, network error, etc. — empty list.
            return []

        out: List[Dict[str, Any]] = []
        for entry in payload:
            loader = entry.get("loader") or {}
            version = loader.get("version")
            if not version:
                continue
            out.append({
                "version": version,
                "stable": True,
                "type": "release",
            })
        return out

    # ---------- Install ----------

    def _maven_metadata_url(self) -> str:
        return f"{self.MAVEN_BASE}/{self.INSTALLER_GROUP_PATH}/maven-metadata.xml"

    def _resolve_installer_version(self) -> Optional[str]:
        """Latest stable quilt-installer version per Maven metadata."""
        try:
            response = self.session.get(self._maven_metadata_url(), timeout=15)
            response.raise_for_status()
            text = response.text or ""
        except requests.RequestException as exc:
            print(f"Failed to fetch Quilt installer maven-metadata: {exc}")
            return None
        match = _MAVEN_RELEASE_RE.search(text)
        if not match:
            return None
        return match.group(1).strip() or None

    def _installer_jar_url(self, installer_version: str) -> str:
        return (
            f"{self.MAVEN_BASE}/{self.INSTALLER_GROUP_PATH}/"
            f"{installer_version}/quilt-installer-{installer_version}.jar"
        )

    def _installer_jar_sha1_url(self, installer_version: str) -> str:
        return self._installer_jar_url(installer_version) + ".sha1"

    def _fetch_expected_sha1(self, installer_version: str) -> Optional[str]:
        try:
            response = self.session.get(
                self._installer_jar_sha1_url(installer_version), timeout=15
            )
            response.raise_for_status()
            text = (response.text or "").strip().split()[0].lower()
            return text if len(text) == 40 else None
        except (requests.RequestException, IndexError):
            return None

    def _download_installer_jar(
        self,
        installer_version: str,
        progress_callback: Optional[
            "Callable[[str, Dict[str, Any]], None]"
        ] = None,
    ) -> "tuple[Optional[Path], Optional[str]]":
        """Download and SHA1-verify the installer JAR.

        Returns ``(path, None)`` on success or ``(None, error_message)``.
        """
        import hashlib

        # installer_version is pre-validated at the install() boundary; this
        # extra resolve()+relative_to() is defence-in-depth.
        target = self._resolve_within_install_path(
            f"quilt-installer-{installer_version}.jar"
        )
        hasher = hashlib.sha1()
        try:
            with self.session.get(
                self._installer_jar_url(installer_version), stream=True, timeout=300
            ) as response:
                response.raise_for_status()
                total_size = int(response.headers.get("Content-Length", 0))
                downloaded = 0
                with open(target, "wb") as fh:
                    for chunk in response.iter_content(chunk_size=65536):
                        if chunk:
                            fh.write(chunk)
                            hasher.update(chunk)
                            downloaded += len(chunk)
                            self._report(
                                progress_callback,
                                "downloading_installer",
                                bytes_done=downloaded,
                                bytes_total=total_size,
                            )
        except requests.RequestException as exc:
            target.unlink(missing_ok=True)
            return None, f"Failed to download Quilt installer: {exc}"

        self._report(progress_callback, "verifying")
        expected_sha1 = self._fetch_expected_sha1(installer_version)
        if not expected_sha1:
            print(
                f"WARNING: Quilt installer SHA1 unavailable for "
                f"{installer_version} — proceeding without integrity check."
            )
        if expected_sha1:
            actual = hasher.hexdigest().lower()
            if actual != expected_sha1:
                target.unlink(missing_ok=True)
                return None, (
                    f"SHA1 checksum mismatch for installer JAR: "
                    f"expected {expected_sha1}, got {actual}"
                )

        return target, None

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

        # Whitelist user-controlled mc_version (and any caller-pinned
        # loader_version) BEFORE they land in filenames or subprocess args
        # — Quilt's installer takes mc_version directly on the command line,
        # so this is the trust-boundary check that closes the S5 vector.
        try:
            validate_version_token(mc_version, field_name="mc_version")
            if loader_version is not None:
                validate_version_token(
                    loader_version, field_name="loader_version"
                )
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
        installer_version = self._resolve_installer_version()
        if not installer_version:
            msg = (
                "Could not resolve latest Quilt installer version from Maven "
                "metadata. Check network connectivity to maven.quiltmc.org."
            )
            self._report(progress_callback, "failed", error=msg)
            return InstallResult(
                success=False,
                status=InstallStatus.FAILED,
                message=msg,
                details={"mc_version": mc_version},
            )

        try:
            validate_version_token(
                installer_version, field_name="installer_version"
            )
        except ValueError as exc:
            msg = str(exc)
            self._report(progress_callback, "failed", error=msg)
            return InstallResult(
                success=False,
                status=InstallStatus.FAILED,
                message=msg,
                details={
                    "mc_version": mc_version,
                    "installer_version": installer_version,
                },
            )

        installer_jar, dl_error = self._download_installer_jar(
            installer_version, progress_callback=progress_callback
        )
        if not installer_jar or not installer_jar.exists():
            msg = dl_error or "Failed to download Quilt installer JAR."
            self._report(progress_callback, "failed", error=msg)
            return InstallResult(
                success=False,
                status=InstallStatus.FAILED,
                message=msg,
                details={
                    "mc_version": mc_version,
                    "installer_version": installer_version,
                },
            )

        # Re-check that ``self.install_path`` resolves under itself before
        # passing it to the subprocess as ``--install-dir=``. ``install_path``
        # is constructed by the install/register routes from a vetted server
        # record, but defence-in-depth: the helper makes the contract explicit
        # and refuses to invoke the subprocess if a future caller hands us a
        # path that escapes its own root (symlink shenanigans, etc.).
        install_dir = self._resolve_within_install_path()
        java_cmd = self.java_exec or "java"
        self._report(progress_callback, "running_installer")
        try:
            completed = subprocess.run(
                [
                    java_cmd, "-jar", str(installer_jar),
                    "install", "server", mc_version,
                    "--download-server",
                    f"--install-dir={install_dir}",
                ],
                cwd=str(self.install_path),
                capture_output=True,
                text=True,
                timeout=1800,
                **platform_utils.subprocess_no_window_kwargs(),
            )
        except subprocess.TimeoutExpired as exc:
            msg = f"Quilt installer timed out: {exc}"
            self._report(progress_callback, "failed", error=msg)
            return InstallResult(
                success=False,
                status=InstallStatus.FAILED,
                message=msg,
                details={
                    "mc_version": mc_version,
                    "installer_version": installer_version,
                },
            )
        except OSError as exc:
            msg = f"Failed to invoke Quilt installer: {exc}"
            self._report(progress_callback, "failed", error=msg)
            return InstallResult(
                success=False,
                status=InstallStatus.FAILED,
                message=msg,
                details={
                    "mc_version": mc_version,
                    "installer_version": installer_version,
                },
            )

        if completed.returncode != 0:
            tail = (completed.stderr or completed.stdout or "").strip().splitlines()
            tail_str = tail[-1] if tail else f"returncode {completed.returncode}"
            msg = f"Quilt installer failed: {tail_str}"
            self._report(progress_callback, "failed", error=msg)
            return InstallResult(
                success=False,
                status=InstallStatus.FAILED,
                message=msg,
                details={
                    "mc_version": mc_version,
                    "installer_version": installer_version,
                    "returncode": completed.returncode,
                },
            )

        self._report(progress_callback, "detecting_artifacts")
        launch_jar = self._resolve_within_install_path(self.LAUNCH_JAR_NAME)
        if not launch_jar.exists():
            msg = (
                "Quilt installer reported success but the expected "
                f"{self.LAUNCH_JAR_NAME} was not produced in the install "
                "directory."
            )
            self._report(progress_callback, "failed", error=msg)
            return InstallResult(
                success=False,
                status=InstallStatus.FAILED,
                message=msg,
                details={
                    "mc_version": mc_version,
                    "installer_version": installer_version,
                },
            )

        self._report(progress_callback, "writing_eula")
        self._write_eula(accepted=True)

        self._report(progress_callback, "done")
        return InstallResult(
            success=True,
            status=InstallStatus.COMPLETED,
            message=f"Quilt installed for MC {mc_version}",
            server_jar=launch_jar,
            details={
                "mc_version": mc_version,
                "installer_version": installer_version,
                "launch_jar": str(launch_jar),
                "install_path": str(self.install_path),
            },
            launch=LaunchSpec(
                type="jar",
                jar=self.LAUNCH_JAR_NAME,
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
