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
        except requests.RequestException as exc:
            print(f"Failed to fetch Forge promotions: {exc}")
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
            {"version": mc, "stable": True, "type": "release"}
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

    # ---------- Install (Task 2 fills in) ----------

    def install(
        self,
        mc_version: str,
        loader_version: Optional[str] = None,
    ) -> InstallResult:
        return InstallResult(
            success=False,
            status=InstallStatus.FAILED,
            message="Forge install not yet implemented (Phase 3b.1 T2).",
        )

    def install_with_config(
        self,
        mc_version: str,
        server_config: Dict[str, Any],
        loader_version: Optional[str] = None,
    ) -> InstallResult:
        return self.install(mc_version, loader_version)
