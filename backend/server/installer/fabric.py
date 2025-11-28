"""Fabric server installer using the Fabric Meta API."""
import requests
from pathlib import Path
from typing import List, Optional, Dict, Any

from .base import InstallerBase, InstallResult, InstallStatus


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
            return response.json()
        except requests.RequestException as exc:
            print(f"Failed to fetch game versions: {exc}")
            return []

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
        installer_version: str
    ) -> Optional[Path]:
        """Download the Fabric server JAR.
        
        Args:
            mc_version: Minecraft version
            loader_version: Fabric loader version
            installer_version: Fabric installer version
            
        Returns:
            Path to downloaded JAR or None on failure
        """
        url = self._get_server_jar_url(mc_version, loader_version, installer_version)
        jar_name = f"fabric-server-mc.{mc_version}-loader.{loader_version}-launcher.jar"
        jar_path = self.install_path / jar_name
        
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
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            jar_file.write(chunk)
                            downloaded += len(chunk)
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

    def _create_server_jar_symlink(self, actual_jar: Path) -> Path:
        """Create a server.jar symlink pointing to the actual JAR.
        
        Args:
            actual_jar: Path to the actual server JAR
            
        Returns:
            Path to server.jar symlink
        """
        server_jar = self.install_path / "server.jar"
        
        # Remove existing symlink or file
        if server_jar.exists() or server_jar.is_symlink():
            server_jar.unlink()
        
        # Create relative symlink
        server_jar.symlink_to(actual_jar.name)
        return server_jar

    def install(
        self,
        mc_version: str,
        loader_version: Optional[str] = None,
        installer_version: Optional[str] = None
    ) -> InstallResult:
        """Install a Fabric server.
        
        Args:
            mc_version: Minecraft version to install
            loader_version: Optional specific loader version (uses latest stable if None)
            installer_version: Optional specific installer version (uses latest stable if None)
            
        Returns:
            InstallResult with success status and details
        """
        print(f"Installing Fabric server for MC {mc_version}")
        
        # Ensure install directory exists
        self._ensure_install_dir()
        
        # Get loader version if not specified
        if not loader_version:
            print("Fetching latest stable loader version...")
            loader_version = self._get_latest_loader_version(mc_version)
            if not loader_version:
                return InstallResult(
                    success=False,
                    status=InstallStatus.FAILED,
                    message=f"Could not find Fabric loader for MC {mc_version}",
                    details={"mc_version": mc_version}
                )
        
        print(f"Using loader version: {loader_version}")

        # Get installer version if not specified
        if not installer_version:
            print("Fetching latest stable installer version...")
            installer_version = self._get_latest_installer_version()
            if not installer_version:
                return InstallResult(
                    success=False,
                    status=InstallStatus.FAILED,
                    message=(
                        "Could not determine Fabric installer version. "
                        "Check network connectivity or Fabric Meta availability."
                    ),
                    details={"mc_version": mc_version, "loader_version": loader_version}
                )

        print(f"Using installer version: {installer_version}")
        
        # Download server JAR
        print("Downloading server JAR...")
        jar_path = self._download_server_jar(mc_version, loader_version, installer_version)
        
        if not jar_path or not jar_path.exists():
            return InstallResult(
                success=False,
                status=InstallStatus.FAILED,
                message="Failed to download Fabric server JAR",
                details={
                    "mc_version": mc_version,
                    "loader_version": loader_version
                }
            )
        
        # Create server.jar symlink
        server_jar = self._create_server_jar_symlink(jar_path)
        
        # Write eula.txt
        print("Writing eula.txt...")
        self._write_eula(accepted=True)
        
        return InstallResult(
            success=True,
            status=InstallStatus.COMPLETED,
            message=f"Fabric server installed successfully",
            server_jar=server_jar,
            details={
                "mc_version": mc_version,
                "loader_version": loader_version,
                "installer_version": installer_version,
                "jar_file": str(jar_path),
                "install_path": str(self.install_path)
            }
        )

    def install_with_config(
        self,
        mc_version: str,
        server_config: Dict[str, Any],
        loader_version: Optional[str] = None,
        installer_version: Optional[str] = None
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
        result = self.install(mc_version, loader_version, installer_version)
        
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
