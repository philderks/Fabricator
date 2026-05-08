"""NeoForge server installer using the NeoForged Maven repo + installer JAR."""
from __future__ import annotations

import re
import requests
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .base import (
    InstallerBase,
    InstallResult,
    InstallStatus,
    LaunchSpec,
)


_VERSION_SUFFIX_RE = re.compile(r"-(beta|rc\d*|pre\d*)$", re.IGNORECASE)


class NeoForgeInstaller(InstallerBase):
    """Installer for NeoForge modded servers.

    NeoForge ships its installer as a runnable JAR. We download it from
    the NeoForged Maven repo, then invoke ``java -jar <installer>
    --installServer`` as a subprocess to materialise the install tree.

    The installer produces a ``run.sh``/``run.bat`` plus
    ``libraries/net/neoforged/neoforge/<version>/{unix,win}_args.txt``.
    We persist the platform-specific args-file path in
    ``LaunchSpec.args_file``; ``ServerProcessRegistry._build_command``
    then boots via ``@<args_file>``.
    """

    MAVEN_BASE = "https://maven.neoforged.net"
    MAVEN_VERSIONS_URL = (
        f"{MAVEN_BASE}/api/maven/versions/releases/net/neoforged/neoforge"
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
        return "neoforge"

    @property
    def requires_java_for_install(self) -> bool:
        return True

    # ---------- Version listing ----------

    def _fetch_maven_versions(self) -> List[str]:
        try:
            response = self.session.get(self.MAVEN_VERSIONS_URL, timeout=15)
            response.raise_for_status()
            payload = response.json()
            return list(payload.get("versions") or [])
        except requests.RequestException as exc:
            print(f"Failed to fetch NeoForge versions: {exc}")
            return []

    @staticmethod
    def _split_version(neoforge_version: str) -> Tuple[Optional[List[int]], bool]:
        """Return (numeric_parts, stable) or (None, _) on parse failure."""
        raw = neoforge_version.strip()
        stable = _VERSION_SUFFIX_RE.search(raw) is None
        base = _VERSION_SUFFIX_RE.sub("", raw)
        try:
            parts = [int(p) for p in base.split(".")]
        except ValueError:
            return None, stable
        if len(parts) < 2:
            return None, stable
        return parts, stable

    @classmethod
    def _neoforge_to_mc_version(cls, neoforge_version: str) -> Optional[str]:
        """Map a NeoForge version to its Minecraft version, or None if unparseable.

        Driven by part-count, not by a numeric threshold on the major:
        - 3-part NeoForge (X.Y.Z) corresponds to classic ``1.X.Y`` MC.
        - 4-part NeoForge (XX.Y.Z.W) corresponds to year-versioned ``XX.Y.Z`` MC.
        """
        parts, _ = cls._split_version(neoforge_version)
        if parts is None:
            return None
        if len(parts) == 3:
            return f"1.{parts[0]}.{parts[1]}"
        if len(parts) == 4:
            return f"{parts[0]}.{parts[1]}.{parts[2]}"
        return None

    @staticmethod
    def _is_mc_version_supported(mc_version: str) -> bool:
        """NeoForge supports MC >= 1.20.2 (and any year-versioned MC)."""
        try:
            major, minor, *rest = [int(p) for p in mc_version.split(".")]
        except ValueError:
            return False
        if major != 1:
            return True
        if minor > 20:
            return True
        if minor == 20:
            patch = rest[0] if rest else 0
            return patch >= 2
        return False

    def get_minecraft_versions(self) -> List[Dict[str, Any]]:
        """Normalised MC versions supported by NeoForge.

        For each MC version, ``stable=True`` iff at least one *stable*
        NeoForge release exists for that MC version. Beta-only MC
        versions surface with ``stable=False``.
        """
        raw = self._fetch_maven_versions()
        per_mc_stable: Dict[str, bool] = {}
        for nf in raw:
            mc = self._neoforge_to_mc_version(nf)
            if not mc or not self._is_mc_version_supported(mc):
                continue
            _, stable = self._split_version(nf)
            per_mc_stable[mc] = per_mc_stable.get(mc, False) or stable

        out: List[Dict[str, Any]] = []
        for mc, stable in per_mc_stable.items():
            out.append({
                "version": mc,
                "stable": stable,
                "type": "release" if stable else "snapshot",
            })

        # Sort descending so newest MC version surfaces first in the UI.
        # Element-wise tuple comparison on parsed segments handles both
        # classic 1.X.Y and year-versioned XX.Y.Z without string tricks.
        def _mc_sort_key(entry):
            try:
                return [int(x) for x in entry["version"].split(".")]
            except ValueError:
                return []

        out.sort(key=_mc_sort_key, reverse=True)
        return out

    def get_available_versions(
        self, mc_version: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """NeoForge versions for ``mc_version``, latest stable first."""
        if not mc_version:
            return []
        raw = self._fetch_maven_versions()
        matching: List[Tuple[str, bool, List[int]]] = []
        for nf in raw:
            if self._neoforge_to_mc_version(nf) != mc_version:
                continue
            parts, stable = self._split_version(nf)
            if parts is None:
                continue
            matching.append((nf, stable, parts))

        matching.sort(key=lambda t: (not t[1], [-x for x in t[2]]))
        return [
            {"version": nf, "stable": stable, "type": "release" if stable else "snapshot"}
            for nf, stable, _ in matching
        ]

    # ---------- Install (Task 6 fills in) ----------

    def install(
        self,
        mc_version: str,
        loader_version: Optional[str] = None,
    ) -> InstallResult:
        return InstallResult(
            success=False,
            status=InstallStatus.FAILED,
            message="NeoForgeInstaller.install not implemented yet",
        )

    def install_with_config(
        self,
        mc_version: str,
        server_config: Dict[str, Any],
        loader_version: Optional[str] = None,
    ) -> InstallResult:
        return self.install(mc_version, loader_version)
