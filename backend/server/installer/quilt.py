"""Quilt server installer.

Pattern: subprocess-driven install, jar-launched runtime.

Install:
    java -jar quilt-installer-<v>.jar install server <mc_version> --download-server

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
from typing import Any, Dict, List, Optional

from backend.utils import platform as platform_utils

from .base import (
    InstallerBase,
    InstallResult,
    InstallStatus,
    LaunchSpec,
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
                "version": version,
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

    # ---------- Install (Task 2 fills in) ----------

    def install(
        self,
        mc_version: str,
        loader_version: Optional[str] = None,
    ) -> InstallResult:
        return InstallResult(
            success=False,
            status=InstallStatus.FAILED,
            message="QuiltInstaller.install not implemented yet",
        )

    def install_with_config(
        self,
        mc_version: str,
        server_config: Dict[str, Any],
        loader_version: Optional[str] = None,
    ) -> InstallResult:
        return self.install(mc_version, loader_version)
