"""Forge server installer (legacy + modern eras).

Pattern: subprocess-driven install. Era is detected post-install by which
artefact the Forge installer produced — we don't predict by MC version
because Forge's transition was gradual and a few patch versions straddle
the boundary.

Era detection (Task 2 fills in):
    Modern (≥1.17):  libraries/net/minecraftforge/forge/<mc>-<build>/{unix,win}_args.txt
                     → LaunchSpec(type="args_file", args_file=...)
    Legacy (≤1.16):  forge-<mc>-<build>.jar (1.13–1.16) or
                     forge-<mc>-<build>-universal.jar (≤1.12.2) in install root
                     → LaunchSpec(type="jar", jar=...)

Boot (via _build_command's existing branches):
    Modern:  java -Xms<m>G -Xmx<m>G @libraries/.../unix_args.txt nogui
    Legacy:  java -Xms<m>G -Xmx<m>G -jar forge-<mc>-<build>.jar nogui

Versions API: https://files.minecraftforge.net/net/minecraftforge/forge/promotions_slim.json
    Returns flat dict of <mc>-{latest,recommended} → <build> pointers.
    Per Forge convention, recommended is preferred (more conservative)
    and latest is a fallback when no recommended exists for a given MC.
"""
from __future__ import annotations

import logging
import re
import requests
import subprocess
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from backend.utils import platform as platform_utils
from backend.utils.platform import is_windows

from .base import (
    InstallerBase,
    InstallResult,
    InstallStatus,
    LaunchSpec,
)


logger = logging.getLogger(__name__)


# Promotion-key shape: "<mc>-latest" or "<mc>-recommended".
_PROMO_KEY_RE = re.compile(r"^(?P<mc>.+?)-(?P<channel>latest|recommended)$")


class ForgeInstaller(InstallerBase):
    PROMOTIONS_URL = (
        "https://files.minecraftforge.net/net/minecraftforge/forge/"
        "promotions_slim.json"
    )
    MAVEN_BASE = "https://maven.minecraftforge.net"
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
        return "forge"

    @property
    def requires_java_for_install(self) -> bool:
        return True

    # ---------- Version listing ----------

    def _fetch_promotions(self) -> Dict[str, str]:
        """Return the flat ``<mc>-channel → build`` dict, or empty on error."""
        try:
            response = self.session.get(self.PROMOTIONS_URL, timeout=15)
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException:
            logger.exception("Failed to fetch Forge promotions")
            return {}
        return dict(payload.get("promos") or {})

    @staticmethod
    def _mc_sort_key(mc_version: str) -> List[int]:
        """Element-wise int parse for descending MC version sort."""
        try:
            return [int(p) for p in mc_version.split(".")]
        except ValueError:
            return []

    def get_minecraft_versions(self) -> List[Dict[str, Any]]:
        """Distinct MC versions Forge supports, newest first.

        Forge has no snapshot/beta channel here; every promotions entry is
        considered ``stable=True`` / ``type="release"``.
        """
        promos = self._fetch_promotions()
        seen: set[str] = set()
        for key in promos:
            match = _PROMO_KEY_RE.match(key)
            if not match:
                continue
            seen.add(match.group("mc"))

        out = [
            {"version": self._canonicalize_mc_version(mc), "stable": True, "type": "release"}
            for mc in seen
        ]
        out.sort(key=lambda v: self._mc_sort_key(v["version"]), reverse=True)
        return out

    def get_available_versions(
        self, mc_version: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Forge build versions for ``mc_version``.

        Returns ``[recommended, latest]`` if both pointers exist, else just
        ``[latest]``. Empty if the MC version isn't in promotions or input
        is None.
        """
        if not mc_version:
            return []
        promos = self._fetch_promotions()
        recommended = promos.get(f"{mc_version}-recommended")
        latest = promos.get(f"{mc_version}-latest")

        out: List[Dict[str, Any]] = []
        if recommended:
            out.append({
                "version": recommended,
                "stable": True,
                "type": "release",
            })
        if latest and latest != recommended:
            out.append({
                "version": latest,
                "stable": True,
                "type": "release",
            })
        return out

    # ---------- Install ----------

    def _select_build_version(self, mc_version: str, promos: Dict[str, str]) -> Optional[str]:
        """Pick the preferred Forge build for ``mc_version``.

        Preference: ``<mc>-recommended`` if present, else ``<mc>-latest``.
        Returns None if neither pointer exists for that MC version.
        """
        recommended = promos.get(f"{mc_version}-recommended")
        if recommended:
            return recommended
        return promos.get(f"{mc_version}-latest")

    def _installer_jar_url(self, mc_version: str, build: str) -> str:
        return (
            f"{self.MAVEN_BASE}/net/minecraftforge/forge/"
            f"{mc_version}-{build}/forge-{mc_version}-{build}-installer.jar"
        )

    def _installer_jar_sha1_url(self, mc_version: str, build: str) -> str:
        return self._installer_jar_url(mc_version, build) + ".sha1"

    def _fetch_expected_sha1(self, mc_version: str, build: str) -> Optional[str]:
        try:
            response = self.session.get(
                self._installer_jar_sha1_url(mc_version, build), timeout=15
            )
            response.raise_for_status()
            text = (response.text or "").strip().split()[0].lower()
            return text if len(text) == 40 else None
        except (requests.RequestException, IndexError):
            return None

    def _download_installer_jar(
        self,
        mc_version: str,
        build: str,
        progress_callback: Optional[
            "Callable[[str, Dict[str, Any]], None]"
        ] = None,
    ) -> "tuple[Optional[Path], Optional[str]]":
        """Download and SHA1-verify the installer JAR.

        Returns ``(path, None)`` on success or ``(None, error_message)``.
        """
        import hashlib

        target = self.install_path / f"forge-{mc_version}-{build}-installer.jar"
        hasher = hashlib.sha1()
        try:
            with self.session.get(
                self._installer_jar_url(mc_version, build), stream=True, timeout=300
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
            return None, f"Failed to download Forge installer: {exc}"

        self._report(progress_callback, "verifying")
        expected_sha1 = self._fetch_expected_sha1(mc_version, build)
        if not expected_sha1:
            logger.warning(
                "Forge installer SHA1 unavailable for %s-%s "
                "— proceeding without integrity check.",
                mc_version,
                build,
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

    def _detect_launch_artifact(
        self, mc_version: str, build: str
    ) -> Optional[LaunchSpec]:
        """Era dispatch by post-install file detection (modern wins on tie).

        Returns ``None`` if neither modern args_file nor legacy launcher jar
        is present in the install directory — the caller turns this into a
        clear "unexpected layout" failure.
        """
        # Modern: libraries/net/minecraftforge/forge/<mc>-<build>/{unix,win}_args.txt
        args_filename = "win_args.txt" if is_windows() else "unix_args.txt"
        modern_args = (
            self.install_path / "libraries" / "net" / "minecraftforge"
            / "forge" / f"{mc_version}-{build}" / args_filename
        )
        if modern_args.exists():
            return LaunchSpec(
                type="args_file",
                args_file=modern_args.relative_to(self.install_path).as_posix(),
                jvm_args=[],
                program_args=["nogui"],
            )

        # Legacy: forge-<mc>-<build>.jar (1.13–1.16) or
        # forge-<mc>-<build>-universal.jar (≤1.12).
        for candidate_name in (
            f"forge-{mc_version}-{build}.jar",
            f"forge-{mc_version}-{build}-universal.jar",
        ):
            candidate = self.install_path / candidate_name
            if candidate.exists():
                return LaunchSpec(
                    type="jar",
                    jar=candidate_name,
                    jvm_args=[],
                    program_args=["nogui"],
                )

        return None

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

        self._report(progress_callback, "resolving_versions")
        promos = self._fetch_promotions()
        if not promos:
            msg = "Could not fetch Forge promotions list. Check connectivity."
            self._report(progress_callback, "failed", error=msg)
            return InstallResult(
                success=False,
                status=InstallStatus.FAILED,
                message=msg,
                details={"mc_version": mc_version},
            )

        build = loader_version or self._select_build_version(mc_version, promos)
        if not build:
            msg = f"No Forge release found for Minecraft {mc_version}."
            self._report(progress_callback, "failed", error=msg)
            return InstallResult(
                success=False,
                status=InstallStatus.FAILED,
                message=msg,
                details={"mc_version": mc_version},
            )

        installer_jar, dl_error = self._download_installer_jar(
            mc_version, build, progress_callback=progress_callback
        )
        if not installer_jar or not installer_jar.exists():
            msg = dl_error or "Failed to download Forge installer JAR."
            self._report(progress_callback, "failed", error=msg)
            return InstallResult(
                success=False,
                status=InstallStatus.FAILED,
                message=msg,
                details={"mc_version": mc_version, "loader_version": build},
            )

        # Run the installer subprocess. EXPLICIT --installServer <path>: the
        # Forge installer's documented form takes a path argument and we use
        # it defensively. Quilt commit 541f26a established this pattern after
        # cwd-only invocation broke when the Quilt installer changed default
        # behaviour to write into a `server/` subdirectory. Forge's installer
        # writes to cwd by default today, but the explicit path is robust to
        # future changes.
        java_cmd = self.java_exec or "java"
        self._report(progress_callback, "running_installer")
        try:
            completed = subprocess.run(
                [
                    java_cmd, "-jar", str(installer_jar),
                    "--installServer", str(self.install_path),
                ],
                cwd=str(self.install_path),
                capture_output=True,
                text=True,
                timeout=1800,
                **platform_utils.subprocess_no_window_kwargs(),
            )
        except subprocess.TimeoutExpired as exc:
            msg = f"Forge installer timed out: {exc}"
            self._report(progress_callback, "failed", error=msg)
            return InstallResult(
                success=False,
                status=InstallStatus.FAILED,
                message=msg,
                details={"mc_version": mc_version, "loader_version": build},
            )
        except OSError as exc:
            msg = f"Failed to invoke Forge installer: {exc}"
            self._report(progress_callback, "failed", error=msg)
            return InstallResult(
                success=False,
                status=InstallStatus.FAILED,
                message=msg,
                details={"mc_version": mc_version, "loader_version": build},
            )

        if completed.returncode != 0:
            tail = (completed.stderr or completed.stdout or "").strip().splitlines()
            tail_str = tail[-1] if tail else f"returncode {completed.returncode}"
            msg = f"Forge installer failed: {tail_str}"
            self._report(progress_callback, "failed", error=msg)
            return InstallResult(
                success=False,
                status=InstallStatus.FAILED,
                message=msg,
                details={
                    "mc_version": mc_version,
                    "loader_version": build,
                    "returncode": completed.returncode,
                },
            )

        self._report(progress_callback, "detecting_artifacts")
        launch = self._detect_launch_artifact(mc_version, build)
        if launch is None:
            msg = (
                "Forge installer reported success but produced unexpected "
                "layout. Expected either "
                f"libraries/net/minecraftforge/forge/{mc_version}-{build}/"
                "{unix,win}_args.txt (modern) or "
                f"forge-{mc_version}-{build}[-universal].jar (legacy) in "
                "install root."
            )
            self._report(progress_callback, "failed", error=msg)
            return InstallResult(
                success=False,
                status=InstallStatus.FAILED,
                message=msg,
                details={"mc_version": mc_version, "loader_version": build},
            )

        self._report(progress_callback, "writing_eula")
        self._write_eula(accepted=True)

        self._report(progress_callback, "done")
        return InstallResult(
            success=True,
            status=InstallStatus.COMPLETED,
            message=f"Forge {build} installed for MC {mc_version}",
            server_jar=None,
            details={
                "mc_version": mc_version,
                "loader_version": build,
                "installer_jar": str(installer_jar),
                "launch_type": launch.type,
                "install_path": str(self.install_path),
            },
            launch=launch,
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
