"""NeoForge server installer using the NeoForged Maven repo + installer JAR."""
from __future__ import annotations

import logging
import re
import requests
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from .base import (
    HashVerifyError,
    InstallerBase,
    InstallResult,
    InstallStatus,
    LaunchSpec,
    SubprocessTimeout,
    _validate_version_token,
    download_with_hash_verify,
    request_with_retry,
    run_subprocess_streaming,
)
from backend.utils import platform as platform_utils
from backend.utils.platform import is_windows


logger = logging.getLogger(__name__)


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
        """Return the NeoForged Maven version list, ``[]`` on hard failure.

        Retry-wrapped (B12b): NeoForged Maven shares the same transient-5xx
        pattern as the Forge Maven; idempotent GET so retry-with-backoff is
        safe.
        """
        def _do_request() -> Dict[str, Any]:
            response = self.session.get(self.MAVEN_VERSIONS_URL, timeout=15)
            response.raise_for_status()
            return response.json()

        try:
            payload = request_with_retry(
                _do_request,
                retries=3,
                on_retry=lambda attempt, exc: logger.warning(
                    "Retrying NeoForge Maven versions fetch (attempt %d): %s",
                    attempt, exc,
                ),
            )
        except requests.RequestException as exc:
            logger.warning("Failed to fetch NeoForge versions: %s", exc)
            return []
        return list(payload.get("versions") or [])

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

        The result is canonicalized via ``_canonicalize_mc_version`` so that
        x.y.0 maps to the bare ``x.y`` form. This keeps the comparison sites
        in ``_select_loader_version`` and ``get_available_versions`` matching
        the canonical strings emitted by ``get_minecraft_versions``.
        """
        parts, _ = cls._split_version(neoforge_version)
        if parts is None:
            return None
        if len(parts) == 3:
            return cls._canonicalize_mc_version(f"1.{parts[0]}.{parts[1]}")
        if len(parts) == 4:
            return cls._canonicalize_mc_version(f"{parts[0]}.{parts[1]}.{parts[2]}")
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
        """Resolve the expected installer-jar SHA1 from NeoForged Maven.

        Same defensive empty-body / non-hex parse as
        :meth:`ForgeInstaller._fetch_expected_sha1` (B12b). Retry-wrapped on
        transient 5xx because Maven outages are observed in the wild.
        """
        def _do_request() -> requests.Response:
            response = self.session.get(
                self._installer_jar_sha1_url(loader_version), timeout=15
            )
            response.raise_for_status()
            return response

        try:
            response = request_with_retry(
                _do_request,
                retries=3,
                on_retry=lambda attempt, exc: logger.warning(
                    "Retrying NeoForge SHA1 fetch for %s (attempt %d): %s",
                    loader_version, attempt, exc,
                ),
            )
        except requests.RequestException:
            return None

        text = (response.text or "").strip()
        if not text:
            return None
        parts = text.split()
        if not parts:
            return None
        sha1_token = parts[0].lower()
        if len(sha1_token) != 40 or not all(
            c in "0123456789abcdef" for c in sha1_token
        ):
            return None
        return sha1_token

    def _download_installer_jar(
        self,
        loader_version: str,
        progress_callback: Optional[
            "Callable[[str, Dict[str, Any]], None]"
        ] = None,
    ) -> "tuple[Optional[Path], Optional[str]]":
        """Download and SHA1-verify the installer JAR.

        S7 hardening (B11): the SHA1 must be available BEFORE the download,
        and a missing SHA1 hard-fails the install instead of silently
        degrading to an unverified payload — NeoForge installer JARs are
        ``java -jar`` payloads, so an unverified install equals arbitrary
        code execution from the Maven path.

        Returns ``(path, None)`` on success or ``(None, error_message)``.
        """
        # loader_version is pre-validated at the install() boundary; this
        # extra resolve()+relative_to() is defence-in-depth.
        target = self._resolve_within_install_path(
            f"neoforge-{loader_version}-installer.jar"
        )

        # Resolve the expected SHA1 first so we can hard-fail before doing
        # the (potentially large) JAR download. A None return from
        # ``_fetch_expected_sha1`` (transient 404 / Maven hiccup / endpoint
        # drift) aborts the install instead of skipping verification.
        expected_sha1 = self._fetch_expected_sha1(loader_version)
        if not expected_sha1:
            return None, (
                f"Could not retrieve NeoForge installer SHA1 for "
                f"{loader_version} from Maven; refusing to install without "
                f"an integrity check."
            )

        def _emit(bytes_done: int, bytes_total: int) -> None:
            self._report(
                progress_callback,
                "downloading_installer",
                bytes_done=bytes_done,
                bytes_total=bytes_total,
            )

        try:
            download_with_hash_verify(
                self._installer_jar_url(loader_version),
                target,
                sha1=expected_sha1,
                session=self.session,
                timeout=300,
                progress_callback=_emit,
                # B12b: retry transient 5xx / connection-resets on the JAR
                # download. HashVerifyError is never retried (cryptographic
                # mismatch is non-transient by definition).
                retries=3,
            )
        except HashVerifyError as exc:
            return None, str(exc)
        except requests.RequestException as exc:
            return None, f"Failed to download NeoForge installer: {exc}"
        except OSError as exc:
            return None, f"Failed to write NeoForge installer: {exc}"

        self._report(progress_callback, "verifying")
        return target, None

    def _detect_args_file(self, loader_version: str) -> Optional[Path]:
        """Return the platform-specific args file produced by --installServer.

        ``loader_version`` is pre-validated at the install() boundary, so the
        path build is trusted; the resolve()+relative_to() check inside
        ``_resolve_within_install_path`` keeps callers honest if they reach
        this method without going through install() first.
        """
        filename = "win_args.txt" if is_windows() else "unix_args.txt"
        candidate = self._resolve_within_install_path(
            "libraries", "net", "neoforged", "neoforge",
            loader_version, filename,
        )
        return candidate if candidate.exists() else None

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
        # loader_version) BEFORE they land in filenames or subprocess args.
        # Auto-resolved loader_version from Maven is validated immediately
        # after lookup — Maven's payload is third-party and treated as
        # untrusted at the same trust-boundary.
        try:
            _validate_version_token(mc_version, field_name="mc_version")
            if loader_version is not None:
                _validate_version_token(
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

        # Resolve loader_version if not pinned.
        self._report(progress_callback, "resolving_versions")
        if not loader_version:
            raw = self._fetch_maven_versions()
            if not raw:
                msg = "Could not fetch NeoForge version list from Maven."
                self._report(progress_callback, "failed", error=msg)
                return InstallResult(
                    success=False,
                    status=InstallStatus.FAILED,
                    message=msg,
                )
            loader_version = self._select_loader_version(mc_version, raw)
            if not loader_version:
                msg = f"No NeoForge release found for Minecraft {mc_version}."
                self._report(progress_callback, "failed", error=msg)
                return InstallResult(
                    success=False,
                    status=InstallStatus.FAILED,
                    message=msg,
                    details={"mc_version": mc_version},
                )
            try:
                _validate_version_token(
                    loader_version, field_name="loader_version"
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
                        "loader_version": loader_version,
                    },
                )

        # Download the installer JAR.
        installer_jar, dl_error = self._download_installer_jar(
            loader_version, progress_callback=progress_callback
        )
        if not installer_jar or not installer_jar.exists():
            msg = dl_error or "Failed to download NeoForge installer JAR."
            self._report(progress_callback, "failed", error=msg)
            return InstallResult(
                success=False,
                status=InstallStatus.FAILED,
                message=msg,
                details={"mc_version": mc_version, "loader_version": loader_version},
            )

        # Run the installer subprocess. cwd=install_path so it materialises
        # libraries/, run.sh, etc. relative to our managed dir. We honour
        # self.java_exec (set by the route via set_java_exec) so the
        # subprocess uses Fabricator's managed Java / per-server javaPath
        # override, not whatever ``java`` happens to be first on PATH.
        #
        # Streaming runner (B12a): forwards each stdout/stderr line live to
        # ``logger.info`` and guarantees a clean kill + drain on timeout —
        # the previous ``subprocess.run(..., timeout=1800)`` raised
        # ``TimeoutExpired`` but could leave the child JVM running and pipes
        # attached, producing a zombie process under load.
        java_cmd = self.java_exec or "java"
        self._report(progress_callback, "running_installer")
        try:
            completed = run_subprocess_streaming(
                [java_cmd, "-jar", str(installer_jar), "--installServer"],
                cwd=Path(self.install_path),
                timeout=1800,
                on_line=lambda line: logger.info("neoforge-installer: %s", line),
                **platform_utils.subprocess_no_window_kwargs(),
            )
        except SubprocessTimeout as exc:
            msg = f"NeoForge installer timed out: {exc}"
            self._report(progress_callback, "failed", error=msg)
            return InstallResult(
                success=False,
                status=InstallStatus.FAILED,
                message=msg,
                details={"mc_version": mc_version, "loader_version": loader_version},
            )
        except OSError as exc:
            msg = f"Failed to invoke NeoForge installer: {exc}"
            self._report(progress_callback, "failed", error=msg)
            return InstallResult(
                success=False,
                status=InstallStatus.FAILED,
                message=msg,
                details={"mc_version": mc_version, "loader_version": loader_version},
            )

        if completed.returncode != 0:
            # Streaming logger already forwarded every line; surface the last
            # few for the InstallResult message without dumping megabytes.
            tail = (completed.stderr or completed.stdout or "").strip().splitlines()
            tail_str = (
                " | ".join(tail[-3:]) if tail else f"returncode {completed.returncode}"
            )
            msg = f"NeoForge installer failed: {tail_str}"
            self._report(progress_callback, "failed", error=msg)
            return InstallResult(
                success=False,
                status=InstallStatus.FAILED,
                message=msg,
                details={
                    "mc_version": mc_version,
                    "loader_version": loader_version,
                    "returncode": completed.returncode,
                },
            )

        # Locate the platform-specific args file.
        self._report(progress_callback, "detecting_artifacts")
        args_file_path = self._detect_args_file(loader_version)
        if not args_file_path:
            msg = (
                "NeoForge installer reported success but the expected "
                "args_file was not found under "
                f"libraries/net/neoforged/neoforge/{loader_version}/."
            )
            self._report(progress_callback, "failed", error=msg)
            return InstallResult(
                success=False,
                status=InstallStatus.FAILED,
                message=msg,
                details={"mc_version": mc_version, "loader_version": loader_version},
            )

        relative_args_file = args_file_path.relative_to(
            self.install_path.resolve()
        ).as_posix()

        self._report(progress_callback, "writing_eula")
        self._write_eula(accepted=True)

        self._report(progress_callback, "done")
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
