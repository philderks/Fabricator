"""NeoForge server installer using the NeoForged Maven repo + installer JAR."""
from __future__ import annotations

import re
import subprocess
import requests
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .base import (
    InstallerBase,
    InstallResult,
    InstallStatus,
    LaunchSpec,
)
from backend.utils import platform as platform_utils
from backend.utils.platform import is_windows


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

    # ---------- Install ----------

    def _select_loader_version(
        self, mc_version: str, raw_versions: List[str]
    ) -> Optional[str]:
        """Pick the latest stable NeoForge version for ``mc_version``.

        Falls back to the latest non-stable version if no stable one exists
        for that MC version (rare, but happens during a snapshot cycle).
        """
        candidates: List[Tuple[str, bool, List[int]]] = []
        for nf in raw_versions:
            if self._neoforge_to_mc_version(nf) != mc_version:
                continue
            parts, stable = self._split_version(nf)
            if parts is None:
                continue
            candidates.append((nf, stable, parts))
        if not candidates:
            return None
        candidates.sort(key=lambda t: (not t[1], [-x for x in t[2]]))
        return candidates[0][0]

    def _installer_jar_url(self, loader_version: str) -> str:
        return (
            f"{self.MAVEN_BASE}/releases/net/neoforged/neoforge/"
            f"{loader_version}/neoforge-{loader_version}-installer.jar"
        )

    def _installer_jar_sha1_url(self, loader_version: str) -> str:
        return self._installer_jar_url(loader_version) + ".sha1"

    def _fetch_expected_sha1(self, loader_version: str) -> Optional[str]:
        try:
            response = self.session.get(
                self._installer_jar_sha1_url(loader_version), timeout=15
            )
            response.raise_for_status()
            text = (response.text or "").strip().split()[0].lower()
            return text if len(text) == 40 else None
        except (requests.RequestException, IndexError):
            return None

    def _download_installer_jar(
        self, loader_version: str
    ) -> "tuple[Optional[Path], Optional[str]]":
        """Download and SHA1-verify the installer JAR.

        Returns ``(path, None)`` on success or ``(None, error_message)``.
        """
        import hashlib

        target = self.install_path / f"neoforge-{loader_version}-installer.jar"
        hasher = hashlib.sha1()
        try:
            with self.session.get(
                self._installer_jar_url(loader_version), stream=True, timeout=300
            ) as response:
                response.raise_for_status()
                with open(target, "wb") as fh:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            fh.write(chunk)
                            hasher.update(chunk)
        except requests.RequestException as exc:
            target.unlink(missing_ok=True)
            return None, f"Failed to download NeoForge installer: {exc}"

        expected_sha1 = self._fetch_expected_sha1(loader_version)
        if not expected_sha1:
            print(
                f"WARNING: NeoForge installer SHA1 unavailable for "
                f"{loader_version} — proceeding without integrity check."
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

    def _detect_args_file(self, loader_version: str) -> Optional[Path]:
        """Return the platform-specific args file produced by --installServer."""
        base = (
            self.install_path / "libraries" / "net" / "neoforged"
            / "neoforge" / loader_version
        )
        filename = "win_args.txt" if is_windows() else "unix_args.txt"
        candidate = base / filename
        return candidate if candidate.exists() else None

    def install(
        self,
        mc_version: str,
        loader_version: Optional[str] = None,
    ) -> InstallResult:
        self._ensure_install_dir()

        # Resolve loader_version if not pinned.
        if not loader_version:
            raw = self._fetch_maven_versions()
            if not raw:
                return InstallResult(
                    success=False,
                    status=InstallStatus.FAILED,
                    message="Could not fetch NeoForge version list from Maven.",
                )
            loader_version = self._select_loader_version(mc_version, raw)
            if not loader_version:
                return InstallResult(
                    success=False,
                    status=InstallStatus.FAILED,
                    message=f"No NeoForge release found for Minecraft {mc_version}.",
                    details={"mc_version": mc_version},
                )

        # Download the installer JAR.
        installer_jar, dl_error = self._download_installer_jar(loader_version)
        if not installer_jar or not installer_jar.exists():
            return InstallResult(
                success=False,
                status=InstallStatus.FAILED,
                message=dl_error or "Failed to download NeoForge installer JAR.",
                details={"mc_version": mc_version, "loader_version": loader_version},
            )

        # Run the installer subprocess. cwd=install_path so it materialises
        # libraries/, run.sh, etc. relative to our managed dir. We honour
        # self.java_exec (set by the route via set_java_exec) so the
        # subprocess uses Fabricator's managed Java / per-server javaPath
        # override, not whatever ``java`` happens to be first on PATH.
        java_cmd = self.java_exec or "java"
        try:
            completed = subprocess.run(
                [java_cmd, "-jar", str(installer_jar), "--installServer"],
                cwd=str(self.install_path),
                capture_output=True,
                text=True,
                timeout=600,
                **platform_utils.subprocess_no_window_kwargs(),
            )
        except subprocess.TimeoutExpired as exc:
            return InstallResult(
                success=False,
                status=InstallStatus.FAILED,
                message=f"NeoForge installer timed out: {exc}",
                details={"mc_version": mc_version, "loader_version": loader_version},
            )
        except OSError as exc:
            return InstallResult(
                success=False,
                status=InstallStatus.FAILED,
                message=f"Failed to invoke NeoForge installer: {exc}",
                details={"mc_version": mc_version, "loader_version": loader_version},
            )

        if completed.returncode != 0:
            tail = (completed.stderr or completed.stdout or "").strip().splitlines()
            tail_str = tail[-1] if tail else f"returncode {completed.returncode}"
            return InstallResult(
                success=False,
                status=InstallStatus.FAILED,
                message=f"NeoForge installer failed: {tail_str}",
                details={
                    "mc_version": mc_version,
                    "loader_version": loader_version,
                    "returncode": completed.returncode,
                },
            )

        # Locate the platform-specific args file.
        args_file_path = self._detect_args_file(loader_version)
        if not args_file_path:
            return InstallResult(
                success=False,
                status=InstallStatus.FAILED,
                message=(
                    "NeoForge installer reported success but the expected "
                    "args_file was not found under "
                    f"libraries/net/neoforged/neoforge/{loader_version}/."
                ),
                details={"mc_version": mc_version, "loader_version": loader_version},
            )

        relative_args_file = args_file_path.relative_to(self.install_path).as_posix()

        self._write_eula(accepted=True)

        return InstallResult(
            success=True,
            status=InstallStatus.COMPLETED,
            message=f"NeoForge {loader_version} installed for MC {mc_version}",
            server_jar=None,
            details={
                "mc_version": mc_version,
                "loader_version": loader_version,
                "installer_jar": str(installer_jar),
                "args_file": relative_args_file,
                "install_path": str(self.install_path),
            },
            launch=LaunchSpec(
                type="args_file",
                args_file=relative_args_file,
                jvm_args=[],
                program_args=["nogui"],
            ),
        )

    def install_with_config(
        self,
        mc_version: str,
        server_config: Dict[str, Any],
        loader_version: Optional[str] = None,
    ) -> InstallResult:
        result = self.install(mc_version, loader_version)
        if not result.success:
            return result

        properties = self.generate_server_properties(server_config)
        self._write_server_properties(properties)
        if result.details:
            result.details["server_properties"] = str(
                self.install_path / "server.properties"
            )
        return result
