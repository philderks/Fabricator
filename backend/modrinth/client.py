"""Modrinth API client for fetching mod information."""
import json
import shutil
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List, Any

import requests


class ModrinthApiError(Exception):
    """Raised when Modrinth API request fails."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


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

    def _request(self, method: str, url: str, *, timeout: int = 15, error_context: str, **kwargs) -> requests.Response:
        try:
            response = self.session.request(method, url, timeout=timeout, **kwargs)
            response.raise_for_status()
            return response
        except requests.exceptions.RequestException as exc:
            status_code = getattr(getattr(exc, 'response', None), 'status_code', None)
            raise ModrinthApiError(f"{error_context}: {exc}", status_code=status_code) from exc

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

        response = self._request(
            'get',
            f"{self.BASE_URL}/search",
            params=params,
            timeout=15,
            error_context="Failed to search mods"
        )
        return response.json()

    def search_modpacks(
        self,
        query: str,
        mc_version: Optional[str] = None,
        loader: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
        index: str = "downloads"
    ) -> Dict[str, Any]:
        # Only filter by project type; loader is intentionally excluded because
        # modpacks define their own loader and filtering by it hides most results.
        facets = [["project_type:modpack"]]

        if mc_version:
            facets.append([f"versions:{mc_version}"])

        params = {
            "query": query,
            "limit": min(limit, 100),
            "offset": offset,
            "index": index,
            "facets": json.dumps(facets)
        }

        response = self._request(
            'get',
            f"{self.BASE_URL}/search",
            params=params,
            timeout=15,
            error_context="Failed to search modpacks"
        )
        return response.json()

    def get_mod(self, mod_id: str) -> Dict[str, Any]:
        response = self._request(
            'get',
            f"{self.BASE_URL}/project/{mod_id}",
            timeout=15,
            error_context="Failed to fetch mod"
        )
        return response.json()

    def get_project(self, project_id: str) -> Dict[str, Any]:
        response = self._request(
            'get',
            f"{self.BASE_URL}/project/{project_id}",
            timeout=15,
            error_context="Failed to fetch project"
        )
        return response.json()

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

        response = self._request(
            'get',
            f"{self.BASE_URL}/project/{mod_id}/version",
            params=params if params else None,
            timeout=15,
            error_context="Failed to fetch mod versions"
        )
        return response.json()

    def get_project_versions(
        self,
        project_id: str,
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

        response = self._request(
            'get',
            f"{self.BASE_URL}/project/{project_id}/version",
            params=params if params else None,
            timeout=15,
            error_context="Failed to fetch project versions"
        )
        return response.json()

    def get_version(self, version_id: str) -> Dict[str, Any]:
        response = self._request(
            'get',
            f"{self.BASE_URL}/version/{version_id}",
            timeout=15,
            error_context="Failed to fetch version"
        )
        return response.json()

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

    def resolve_project_version(
        self,
        project_id: str,
        mc_version: Optional[str] = None,
        loader: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        loaders = [loader] if loader else None
        game_versions = [mc_version] if mc_version else None

        versions = self.get_project_versions(
            project_id=project_id,
            loaders=loaders,
            game_versions=game_versions
        )

        best_version = self.pick_best_version(versions)
        if not best_version:
            return None

        return {
            "version": best_version,
            "download_url": self.get_primary_file_url(best_version)
        }

    def download_mod(
        self,
        download_url: str,
        target_folder: Path
    ) -> Optional[Path]:
        try:
            target_folder.mkdir(parents=True, exist_ok=True)
            filename = download_url.split("/")[-1]
            target_path = target_folder / filename

            with self._request(
                'get',
                download_url,
                stream=True,
                timeout=60,
                error_context="Failed to download mod file"
            ) as response:
                with open(target_path, "wb") as file_handle:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            file_handle.write(chunk)

            return target_path
        except OSError as exc:
            raise ModrinthApiError(f"Failed to save mod file: {exc}") from exc

    def install_modpack(
        self,
        project_id: str,
        install_path: Path,
        mc_version: Optional[str] = None,
        loader: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Download and install a modpack into a server directory.

        Downloads the .mrpack file, installs all server-side mod files listed in
        modrinth.index.json, and extracts overrides/ and server-overrides/ into
        the server root. Client-only files (env.server == 'unsupported') are skipped.
        """
        loaders = [loader] if loader else None
        game_versions = [mc_version] if mc_version else None

        versions = self.get_project_versions(
            project_id, loaders=loaders, game_versions=game_versions
        )
        best = self.pick_best_version(versions)

        # Retry without loader filter if no match found
        if not best and loaders:
            versions = self.get_project_versions(
                project_id, loaders=None, game_versions=game_versions
            )
            best = self.pick_best_version(versions)

        # Retry without any filter as last resort
        if not best and (loaders or game_versions):
            versions = self.get_project_versions(project_id)
            best = self.pick_best_version(versions)

        if not best:
            raise ModrinthApiError("No suitable modpack version found")

        download_url = self.get_primary_file_url(best)
        if not download_url:
            raise ModrinthApiError("No download URL found for modpack version")

        install_path = Path(install_path).resolve()
        files_installed: List[str] = []
        files_skipped: List[str] = []
        index: Dict[str, Any] = {}

        with tempfile.TemporaryDirectory() as tmp_dir:
            mrpack_path = Path(tmp_dir) / "modpack.mrpack"

            with self._request(
                'get', download_url, stream=True, timeout=120,
                error_context="Failed to download modpack"
            ) as response:
                with open(mrpack_path, 'wb') as fh:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            fh.write(chunk)

            with zipfile.ZipFile(mrpack_path, 'r') as zf:
                with zf.open('modrinth.index.json') as fh:
                    index = json.loads(fh.read())

                # Install mod files listed in the index
                for entry in index.get('files', []):
                    env = entry.get('env', {})
                    if env.get('server', 'required') == 'unsupported':
                        files_skipped.append(entry['path'])
                        continue

                    target = (install_path / entry['path']).resolve()
                    if not str(target).startswith(str(install_path)):
                        raise ModrinthApiError(
                            f"Invalid path in modpack index: {entry['path']}"
                        )

                    target.parent.mkdir(parents=True, exist_ok=True)
                    downloads = entry.get('downloads', [])
                    if not downloads:
                        continue

                    with self._request(
                        'get', downloads[0], stream=True, timeout=60,
                        error_context=f"Failed to download {entry['path']}"
                    ) as r:
                        with open(target, 'wb') as fh:
                            for chunk in r.iter_content(chunk_size=8192):
                                if chunk:
                                    fh.write(chunk)
                    files_installed.append(entry['path'])

                # Extract overrides and server-overrides into server root
                for member in zf.infolist():
                    if member.is_dir():
                        continue
                    relative: Optional[str] = None
                    for prefix in ('server-overrides/', 'overrides/'):
                        if member.filename.startswith(prefix):
                            relative = member.filename[len(prefix):]
                            break
                    if not relative:
                        continue

                    target = (install_path / relative).resolve()
                    if not str(target).startswith(str(install_path)):
                        continue
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(member) as src, open(target, 'wb') as dst:
                        shutil.copyfileobj(src, dst)

        return {
            'version': best.get('version_number'),
            'name': best.get('name'),
            'files_installed': len(files_installed),
            'files_skipped': len(files_skipped),
            'dependencies': index.get('dependencies', {}),
        }

    def get_categories(self) -> List[Dict[str, Any]]:
        response = self._request(
            'get',
            f"{self.BASE_URL}/tag/category",
            timeout=15,
            error_context="Failed to fetch categories"
        )
        return response.json()

    def get_loaders(self) -> List[Dict[str, Any]]:
        response = self._request(
            'get',
            f"{self.BASE_URL}/tag/loader",
            timeout=15,
            error_context="Failed to fetch loaders"
        )
        return response.json()

    def get_game_versions(self) -> List[Dict[str, Any]]:
        response = self._request(
            'get',
            f"{self.BASE_URL}/tag/game_version",
            timeout=15,
            error_context="Failed to fetch game versions"
        )
        return response.json()
