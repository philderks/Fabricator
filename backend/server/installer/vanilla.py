"""Vanilla server installer using Mojang piston-meta."""
from __future__ import annotations

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
)


class VanillaInstaller(InstallerBase):
    """Installer for vanilla Minecraft servers.

    Uses the Mojang piston-meta version manifest:
    https://piston-meta.mojang.com/mc/game/version_manifest_v2.json
    """

    MANIFEST_URL = (
        "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"
    )
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
        return "vanilla"

    def _fetch_manifest(self) -> Dict[str, Any]:
        response = self.session.get(self.MANIFEST_URL, timeout=15)
        response.raise_for_status()
        return response.json()

    def get_minecraft_versions(self) -> List[Dict[str, Any]]:
        try:
            manifest = self._fetch_manifest()
        except requests.RequestException as exc:
            print(f"Failed to fetch Mojang version manifest: {exc}")
            return []

        out: List[Dict[str, Any]] = []
        for entry in manifest.get("versions", []):
            mc_id = entry.get("id")
            mc_type = entry.get("type", "release")
            if not mc_id:
                continue
            out.append({
                "version": self._canonicalize_mc_version(mc_id),
                "stable": mc_type == "release",
                "type": mc_type,
            })
        return out

    def get_available_versions(
        self, mc_version: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        # Vanilla has no separate loader versions.
        return []

    def _find_version_entry(
        self, mc_version: str, manifest: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        for entry in manifest.get("versions", []):
            if entry.get("id") == mc_version:
                return entry
        return None

    def _fetch_version_meta(self, version_url: str) -> Dict[str, Any]:
        response = self.session.get(version_url, timeout=15)
        response.raise_for_status()
        return response.json()

    def _download_server_jar(
        self,
        server_url: str,
        expected_sha1: Optional[str] = None,
        progress_callback: Optional[
            "Callable[[str, Dict[str, Any]], None]"
        ] = None,
    ) -> "tuple[Optional[Path], Optional[str]]":
        """Download the vanilla server jar and verify its SHA1.

        Mojang's piston-meta always publishes ``downloads.server.sha1`` for
        any version with a server JAR; the caller passes that value in via
        ``expected_sha1`` and the helper hard-fails on mismatch.

        Returns ``(path, None)`` on success, or ``(None, error_message)`` on
        any failure (network error or SHA1 mismatch). The partial jar file
        is removed on failure by ``download_with_hash_verify``.
        """
        jar_path = self.install_path / "server.jar"

        def _emit(bytes_done: int, bytes_total: int) -> None:
            self._report(
                progress_callback,
                "downloading_server_jar",
                bytes_done=bytes_done,
                bytes_total=bytes_total,
            )

        try:
            download_with_hash_verify(
                server_url,
                jar_path,
                sha1=expected_sha1,
                session=self.session,
                timeout=300,
                progress_callback=_emit,
            )
        except HashVerifyError as exc:
            return None, str(exc)
        except requests.RequestException as exc:
            return None, f"Failed to download vanilla server jar: {exc}"
        except OSError as exc:
            return None, f"Failed to write vanilla server jar: {exc}"

        return jar_path, None

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
        try:
            manifest = self._fetch_manifest()
        except requests.RequestException as exc:
            msg = f"Could not fetch Mojang manifest: {exc}"
            self._report(progress_callback, "failed", error=msg)
            return InstallResult(
                success=False,
                status=InstallStatus.FAILED,
                message=msg,
            )

        entry = self._find_version_entry(mc_version, manifest)
        if not entry:
            msg = f"Unknown Minecraft version: {mc_version}"
            self._report(progress_callback, "failed", error=msg)
            return InstallResult(
                success=False,
                status=InstallStatus.FAILED,
                message=msg,
                details={"mc_version": mc_version},
            )

        try:
            version_meta = self._fetch_version_meta(entry["url"])
        except (requests.RequestException, KeyError) as exc:
            msg = f"Could not fetch version metadata: {exc}"
            self._report(progress_callback, "failed", error=msg)
            return InstallResult(
                success=False,
                status=InstallStatus.FAILED,
                message=msg,
                details={"mc_version": mc_version},
            )

        server_dl = (version_meta.get("downloads") or {}).get("server") or {}
        server_url = server_dl.get("url")
        if not server_url:
            msg = (
                f"Minecraft {mc_version} has no server download "
                "(versions older than ~1.2.5 are server-less)."
            )
            self._report(progress_callback, "failed", error=msg)
            return InstallResult(
                success=False,
                status=InstallStatus.FAILED,
                message=msg,
                details={"mc_version": mc_version},
            )

        # Mojang piston-meta publishes ``downloads.server.sha1`` for every
        # version that has a server JAR. Refusing to install when the field
        # is absent closes the integrity gap (S7) — a missing SHA1 means
        # either piston-meta drift or a tampered manifest, neither of which
        # is safe to silently degrade to an unverified install.
        expected_sha1 = server_dl.get("sha1")
        if not expected_sha1:
            msg = (
                f"Mojang manifest for {mc_version} did not publish a "
                "server JAR SHA1; refusing to install without an "
                "integrity check."
            )
            self._report(progress_callback, "failed", error=msg)
            return InstallResult(
                success=False,
                status=InstallStatus.FAILED,
                message=msg,
                details={"mc_version": mc_version},
            )

        jar_path, dl_error = self._download_server_jar(
            server_url,
            expected_sha1=expected_sha1,
            progress_callback=progress_callback,
        )
        if not jar_path or not jar_path.exists():
            msg = dl_error or "Failed to download vanilla server jar"
            self._report(progress_callback, "failed", error=msg)
            return InstallResult(
                success=False,
                status=InstallStatus.FAILED,
                message=msg,
                details={"mc_version": mc_version},
            )

        self._report(progress_callback, "writing_eula")
        self._write_eula(accepted=True)

        self._report(progress_callback, "done")
        return InstallResult(
            success=True,
            status=InstallStatus.COMPLETED,
            message=f"Vanilla {mc_version} installed successfully",
            server_jar=jar_path,
            details={
                "mc_version": mc_version,
                "jar_file": str(jar_path),
                "install_path": str(self.install_path),
                "sha1": expected_sha1,
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
