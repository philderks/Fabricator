"""Fabric server installer using the Fabric Meta API."""
import os
import requests
from pathlib import Path
from typing import Callable, List, Optional, Dict, Any

from .base import InstallerBase, InstallResult, InstallStatus, LaunchSpec, DIR_PERMISSIONS


class FabricInstaller(InstallerBase):
    """Installer for Fabric modded Minecraft servers.
    
    Uses the Fabric Meta API to download pre-built server JARs.
    API Documentation: https://meta.fabricmc.net/
    """

    META_API_BASE = "https://meta.fabricmc.net/v2"
    USER_AGENT = "philderks/Fabricator/1.0.0 (https://github.com/philderks/Fabricator)"

    def __init__(self, install_path: Path):
        """Initialize Fabric installer.
        
        Args:
            install_path: Directory where server will be installed
        """
        super().__init__(install_path)
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": self.USER_AGENT,
            "Accept": "application/json"
        })

    @property
    def loader_name(self) -> str:
        return "fabric"

    def get_minecraft_versions(self) -> List[Dict[str, Any]]:
        """Get Minecraft versions supported by Fabric.

        Returns:
            List of game versions with stability info
        """
        try:
            response = self.session.get(
                f"{self.META_API_BASE}/versions/game",
                timeout=15
            )
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as exc:
            print(f"Failed to fetch game versions: {exc}")
            return []

        out: List[Dict[str, Any]] = []
        for entry in payload:
            v = entry.get("version")
            if not v:
                out.append(entry)
                continue
            normalized = dict(entry)
            normalized["version"] = self._canonicalize_mc_version(v)
            out.append(normalized)
        return out

    def get_available_versions(self, mc_version: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get available Fabric loader versions.
        
        Args:
            mc_version: Minecraft version to get loader versions for
            
        Returns:
            List of loader versions with metadata
        """
        try:
            if mc_version:
                # Get loader versions for specific MC version
                response = self.session.get(
                    f"{self.META_API_BASE}/versions/loader/{mc_version}",
                    timeout=15
                )
            else:
                # Get all loader versions
                response = self.session.get(
                    f"{self.META_API_BASE}/versions/loader",
                    timeout=15
                )
            
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            print(f"Failed to fetch loader versions: {exc}")
            return []

    def get_installer_versions(self) -> List[Dict[str, Any]]:
        """Get available Fabric installer versions.
        
        Returns:
            List of installer versions
        """
        try:
            response = self.session.get(
                f"{self.META_API_BASE}/versions/installer",
                timeout=15
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            print(f"Failed to fetch installer versions: {exc}")
            return []

    def _get_latest_installer_version(self) -> Optional[str]:
        """Get the latest stable Fabric installer version."""
        versions = self.get_installer_versions()
        if not versions:
            return None

        for version in versions:
            if version.get("stable"):
                return version.get("version")

        return versions[0].get("version")

    def _get_latest_loader_version(self, mc_version: str) -> Optional[str]:
        """Get the latest stable loader version for a MC version.
        
        Args:
            mc_version: Minecraft version
            
        Returns:
            Latest loader version string or None
        """
        versions = self.get_available_versions(mc_version)
        if not versions:
            return None
        
        # Versions are sorted by preference, first stable one is best
        for version in versions:
            loader = version.get("loader", {})
            if loader.get("stable", False):
                return loader.get("version")
        
        # Fallback to first version if no stable found
        if versions:
            return versions[0].get("loader", {}).get("version")
        
        return None

    def _get_server_jar_url(
        self,
        mc_version: str,
        loader_version: str,
        installer_version: str
    ) -> str:
        """Get the URL for the pre-built Fabric server JAR.
        
        Args:
            mc_version: Minecraft version
            loader_version: Fabric loader version
            installer_version: Fabric installer version
            
        Returns:
            URL to download the server JAR
        """
        return (
            f"{self.META_API_BASE}/versions/loader/"
            f"{mc_version}/{loader_version}/{installer_version}/server/jar"
        )

    def _download_server_jar(
        self,
        mc_version: str,
        loader_version: str,
        installer_version: str,
        progress_callback: Optional[
            "Callable[[str, Dict[str, Any]], None]"
        ] = None,
    ) -> Optional[Path]:
        """Download the Fabric server JAR.

        Args:
            mc_version: Minecraft version
            loader_version: Fabric loader version
            installer_version: Fabric installer version
            progress_callback: Optional ``(phase, detail)`` callback for
                streaming bytes-progress updates.

        Returns:
            Path to downloaded JAR or None on failure
        """
        url = self._get_server_jar_url(mc_version, loader_version, installer_version)
        jar_path = self.install_path / "server.jar"

        try:
            print(f"Downloading Fabric server from: {url}")

            with self.session.get(url, stream=True, timeout=120) as response:
                response.raise_for_status()

                # Check content type
                content_type = response.headers.get("Content-Type", "")
                if "application/java-archive" not in content_type and "application/octet-stream" not in content_type:
                    print(f"Unexpected content type: {content_type}")
                    # Still try to download, sometimes headers are wrong

                total_size = int(response.headers.get("Content-Length", 0))
                downloaded = 0

                with open(jar_path, "wb") as jar_file:
                    for chunk in response.iter_content(chunk_size=65536):
                        if chunk:
                            jar_file.write(chunk)
                            downloaded += len(chunk)
                            self._report(
                                progress_callback,
                                "downloading_server_jar",
                                bytes_done=downloaded,
                                bytes_total=total_size,
                            )
                            if total_size > 0:
                                progress = (downloaded / total_size) * 100
                                print(f"Download progress: {progress:.1f}%", end="\r")

                print(f"\nDownloaded: {jar_path} ({downloaded} bytes)")

            return jar_path

        except requests.RequestException as exc:
            print(f"Download failed: {exc}")
            if jar_path.exists():
                jar_path.unlink()
            return None

    def install(
        self,
        mc_version: str,
        loader_version: Optional[str] = None,
        installer_version: Optional[str] = None,
        progress_callback: Optional[
            "Callable[[str, Dict[str, Any]], None]"
        ] = None,
    ) -> InstallResult:
        """Install a Fabric server.
        
        Args:
            mc_version: Minecraft version to install
            loader_version: Optional specific loader version (uses latest stable if None)
            installer_version: Optional specific installer version (uses latest stable if None)
            
        Returns:
            InstallResult with success status and details
        """
        self._report(progress_callback, "starting")
        print(f"Installing Fabric server for MC {mc_version}")

        # Ensure install directory exists
        self._ensure_install_dir()

        # Get loader version if not specified
        self._report(progress_callback, "resolving_versions")
        if not loader_version:
            print("Fetching latest stable loader version...")
            loader_version = self._get_latest_loader_version(mc_version)
            if not loader_version:
                msg = f"Could not find Fabric loader for MC {mc_version}"
                self._report(progress_callback, "failed", error=msg)
                return InstallResult(
                    success=False,
                    status=InstallStatus.FAILED,
                    message=msg,
                    details={"mc_version": mc_version}
                )

        print(f"Using loader version: {loader_version}")

        # Get installer version if not specified
        if not installer_version:
            print("Fetching latest stable installer version...")
            installer_version = self._get_latest_installer_version()
            if not installer_version:
                msg = (
                    "Could not determine Fabric installer version. "
                    "Check network connectivity or Fabric Meta availability."
                )
                self._report(progress_callback, "failed", error=msg)
                return InstallResult(
                    success=False,
                    status=InstallStatus.FAILED,
                    message=msg,
                    details={"mc_version": mc_version, "loader_version": loader_version}
                )

        print(f"Using installer version: {installer_version}")

        # Download server JAR
        print("Downloading server JAR...")
        jar_path = self._download_server_jar(
            mc_version,
            loader_version,
            installer_version,
            progress_callback=progress_callback,
        )

        if not jar_path or not jar_path.exists():
            msg = "Failed to download Fabric server JAR"
            self._report(progress_callback, "failed", error=msg)
            return InstallResult(
                success=False,
                status=InstallStatus.FAILED,
                message=msg,
                details={
                    "mc_version": mc_version,
                    "loader_version": loader_version
                }
            )

        # Pre-create .fabric cache directory so the launcher can
        # download the vanilla server JAR on first start without
        # running into permission issues.
        fabric_cache = self.install_path / ".fabric"
        fabric_cache.mkdir(exist_ok=True)
        try:
            os.chmod(fabric_cache, DIR_PERMISSIONS)
        except OSError:
            pass

        # Write eula.txt
        print("Writing eula.txt...")
        self._report(progress_callback, "writing_eula")
        self._write_eula(accepted=True)

        self._report(progress_callback, "done")
        return InstallResult(
            success=True,
            status=InstallStatus.COMPLETED,
            message="Fabric server installed successfully",
            server_jar=jar_path,
            details={
                "mc_version": mc_version,
                "loader_version": loader_version,
                "installer_version": installer_version,
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
        installer_version: Optional[str] = None,
        progress_callback: Optional[
            "Callable[[str, Dict[str, Any]], None]"
        ] = None,
    ) -> InstallResult:
        """Install a Fabric server with full configuration.
        
        Args:
            mc_version: Minecraft version to install
            server_config: Server configuration dictionary
            loader_version: Optional specific loader version
            
        Returns:
            InstallResult with success status and details
        """
        # First do the basic installation
        result = self.install(
            mc_version,
            loader_version,
            installer_version,
            progress_callback=progress_callback,
        )
        
        if not result.success:
            return result
        
        # Generate and write server.properties
        print("Writing server.properties...")
        properties = self.generate_server_properties(server_config)
        self._write_server_properties(properties)
        
        # Update result details
        if result.details:
            result.details["server_properties"] = str(self.install_path / "server.properties")
        
        return result
