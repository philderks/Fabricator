"""Modrinth API client for fetching mod information."""
import json
import requests
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List, Any


class ModrinthClient:
    """Client for interacting with the Modrinth API."""
    
    BASE_URL = "https://api.modrinth.com/v2"
    USER_AGENT = "philderks/Fabricator/1.0.0 (https://github.com/philderks/Fabricator)"
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': self.USER_AGENT,
            'Accept': 'application/json'
        })
    
    def search_mods(
        self,
        query: str,
        mc_version: Optional[str] = None,
        loader: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
        index: str = "downloads"
    ) -> Dict[str, Any]:
        """
        Search for mods on Modrinth.
        
        Args:
            query: Search query string
            mc_version: Minecraft version to filter by (e.g., "1.20.1")
            loader: Loader to filter by (e.g., "fabric", "forge")
            limit: Number of results to return (max 100)
            offset: Offset for pagination
            index: Sort index (relevance, downloads, follows, newest, updated)
            
        Returns:
            Dictionary containing search results with hits and metadata
        """
        # Build facets: always filter for project_type:mod
        facets = [["project_type:mod"]]
        
        if loader:
            # In search, loaders are under categories
            facets.append([f"categories:{loader}"])
        
        if mc_version:
            facets.append([f"versions:{mc_version}"])
        
        params = {
            "query": query,
            "limit": min(limit, 100),
            "offset": offset,
            "index": index,
            "facets": json.dumps(facets)
        }
        
        try:
            response = self.session.get(f"{self.BASE_URL}/search", params=params, timeout=15)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            return {"error": str(e), "hits": [], "total_hits": 0}
    
    def get_mod(self, mod_id: str) -> Dict[str, Any]:
        """
        Get detailed information about a specific mod.
        
        Args:
            mod_id: The mod's ID or slug
            
        Returns:
            Dictionary containing mod details
        """
        try:
            response = self.session.get(f"{self.BASE_URL}/project/{mod_id}", timeout=15)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            return {"error": str(e)}
    
    def get_mod_versions(
        self,
        mod_id: str,
        loaders: Optional[List[str]] = None,
        game_versions: Optional[List[str]] = None,
        featured: Optional[bool] = None
    ) -> List[Dict[str, Any]]:
        """
        Get all versions of a mod, optionally filtered by loader and game version.
        
        Args:
            mod_id: The mod's ID or slug
            loaders: List of mod loaders to filter by (e.g., ["fabric", "forge"])
            game_versions: List of game versions to filter by (e.g., ["1.20.1"])
            featured: Filter for featured versions only
            
        Returns:
            List of version dictionaries
        """
        params = {}
        if loaders:
            params["loaders"] = json.dumps(loaders)
        if game_versions:
            params["game_versions"] = json.dumps(game_versions)
        if featured is not None:
            params["featured"] = str(featured).lower()
        
        try:
            response = self.session.get(
                f"{self.BASE_URL}/project/{mod_id}/version",
                params=params if params else None,
                timeout=15
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            return [{"error": str(e)}]
    
    def get_version(self, version_id: str) -> Dict[str, Any]:
        """
        Get detailed information about a specific mod version.
        
        Args:
            version_id: The version ID
            
        Returns:
            Dictionary containing version details
        """
        try:
            response = self.session.get(f"{self.BASE_URL}/version/{version_id}", timeout=15)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            return {"error": str(e)}
    
    def pick_best_version(self, versions: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """
        Pick the best version from a list of versions.
        Prefers release versions and sorts by date published (newest first).
        
        Args:
            versions: List of version dictionaries
            
        Returns:
            Best version dictionary or None if no versions available
        """
        if not versions:
            return None
        
        # Filter out error entries
        valid_versions = [v for v in versions if "error" not in v]
        if not valid_versions:
            return None
        
        # Prefer release versions
        release_versions = [v for v in valid_versions if v.get("version_type") == "release"]
        candidates = release_versions if release_versions else valid_versions
        
        # Sort by date published (newest first)
        def parse_date(v: Dict[str, Any]) -> datetime:
            date_str = v.get("date_published", "")
            try:
                return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                return datetime.min
        
        return sorted(candidates, key=parse_date, reverse=True)[0]
    
    def get_primary_file_url(self, version: Dict[str, Any]) -> Optional[str]:
        """
        Get the download URL of the primary file from a version.
        
        Args:
            version: Version dictionary
            
        Returns:
            Download URL string or None if not found
        """
        files = version.get("files", [])
        if not files:
            return None
        
        # Find primary file or use first file
        primary_files = [f for f in files if f.get("primary")]
        file_obj = primary_files[0] if primary_files else files[0]
        
        return file_obj.get("url")
    
    def get_mod_download_url(
        self,
        mod_id: str,
        mc_version: str,
        loader: str = "fabric"
    ) -> Optional[str]:
        """
        Get the direct download URL for a mod's best matching version.
        
        Args:
            mod_id: The mod's ID or slug
            mc_version: Minecraft version (e.g., "1.20.1")
            loader: Mod loader (e.g., "fabric", "forge")
            
        Returns:
            Direct download URL or None if no suitable version found
        """
        versions = self.get_mod_versions(
            mod_id=mod_id,
            loaders=[loader],
            game_versions=[mc_version]
        )
        
        best_version = self.pick_best_version(versions)
        if not best_version:
            return None
        
        return self.get_primary_file_url(best_version)
    
    def download_mod(
        self,
        download_url: str,
        target_folder: Path
    ) -> Optional[Path]:
        """
        Download a mod file to the target folder.
        
        Args:
            download_url: Direct download URL of the mod file
            target_folder: Path to the folder where the file should be saved
            
        Returns:
            Path to the downloaded file or None if download failed
        """
        try:
            target_folder.mkdir(parents=True, exist_ok=True)
            
            # Extract filename from URL
            filename = download_url.split("/")[-1]
            target_path = target_folder / filename
            
            # Download file
            with self.session.get(download_url, stream=True, timeout=60) as response:
                response.raise_for_status()
                with open(target_path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
            
            return target_path
        except Exception as e:
            print(f"Download failed: {e}")
            return None
    
    def get_categories(self) -> List[Dict[str, Any]]:
        """
        Get all available categories/tags from Modrinth.
        
        Returns:
            List of category dictionaries
        """
        try:
            response = self.session.get(f"{self.BASE_URL}/tag/category")
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            return [{"error": str(e)}]
    
    def get_loaders(self) -> List[Dict[str, Any]]:
        """
        Get all available mod loaders from Modrinth.
        
        Returns:
            List of loader dictionaries
        """
        try:
            response = self.session.get(f"{self.BASE_URL}/tag/loader")
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            return [{"error": str(e)}]
    
    def get_game_versions(self) -> List[Dict[str, Any]]:
        """
        Get all available game versions from Modrinth.
        
        Returns:
            List of game version dictionaries
        """
        try:
            response = self.session.get(f"{self.BASE_URL}/tag/game_version")
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            return [{"error": str(e)}]
