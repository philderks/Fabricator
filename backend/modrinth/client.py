"""Modrinth API client for fetching mod information."""
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List, Any

import requests


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
        facets = [["project_type:mod"]]

        if loader:
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
        except requests.exceptions.RequestException as exc:
            return {"error": str(exc), "hits": [], "total_hits": 0}

    def get_mod(self, mod_id: str) -> Dict[str, Any]:
        try:
            response = self.session.get(f"{self.BASE_URL}/project/{mod_id}", timeout=15)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as exc:
            return {"error": str(exc)}

    def get_mod_versions(
        self,
        mod_id: str,
        loaders: Optional[List[str]] = None,
        game_versions: Optional[List[str]] = None,
        featured: Optional[bool] = None
    ) -> List[Dict[str, Any]]:
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
        except requests.exceptions.RequestException as exc:
            return [{"error": str(exc)}]

    def get_version(self, version_id: str) -> Dict[str, Any]:
        try:
            response = self.session.get(f"{self.BASE_URL}/version/{version_id}", timeout=15)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as exc:
            return {"error": str(exc)}

    def pick_best_version(self, versions: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not versions:
            return None

        valid_versions = [v for v in versions if "error" not in v]
        if not valid_versions:
            return None

        release_versions = [v for v in valid_versions if v.get("version_type") == "release"]
        candidates = release_versions if release_versions else valid_versions

        def parse_date(version: Dict[str, Any]) -> datetime:
            date_str = version.get("date_published", "")
            try:
                return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                return datetime.min

        return sorted(candidates, key=parse_date, reverse=True)[0]

    def get_primary_file_url(self, version: Dict[str, Any]) -> Optional[str]:
        files = version.get("files", [])
        if not files:
            return None

        primary_files = [file for file in files if file.get("primary")]
        file_obj = primary_files[0] if primary_files else files[0]
        return file_obj.get("url")

    def get_mod_download_url(
        self,
        mod_id: str,
        mc_version: str,
        loader: str = "fabric"
    ) -> Optional[str]:
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
        try:
            target_folder.mkdir(parents=True, exist_ok=True)
            filename = download_url.split("/")[-1]
            target_path = target_folder / filename

            with self.session.get(download_url, stream=True, timeout=60) as response:
                response.raise_for_status()
                with open(target_path, "wb") as file_handle:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            file_handle.write(chunk)

            return target_path
        except Exception as exc:
            print(f"Download failed: {exc}")
            return None

    def get_categories(self) -> List[Dict[str, Any]]:
        try:
            response = self.session.get(f"{self.BASE_URL}/tag/category")
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as exc:
            return [{"error": str(exc)}]

    def get_loaders(self) -> List[Dict[str, Any]]:
        try:
            response = self.session.get(f"{self.BASE_URL}/tag/loader")
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as exc:
            return [{"error": str(exc)}]

    def get_game_versions(self) -> List[Dict[str, Any]]:
        try:
            response = self.session.get(f"{self.BASE_URL}/tag/game_version")
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as exc:
            return [{"error": str(exc)}]
