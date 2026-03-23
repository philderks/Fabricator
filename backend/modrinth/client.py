"""Modrinth API client for fetching mod and modpack information."""
import json
import shutil
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

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
    MODPACK_SWITCH_PATHS = (
        'mods',
        'config',
        'defaultconfigs',
        'kubejs',
        'scripts',
        'resourcepacks',
        'shaderpacks',
    )
    # Keep this list minimal and focused on known dedicated-server hard failures.
    SERVER_BLOCKED_MOD_IDS = {
        'mod-loading-screen',
    }

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
            response = getattr(exc, 'response', None)
            status_code = getattr(response, 'status_code', None)

            detail = ''
            if response is not None:
                try:
                    payload = response.json()
                    detail = payload.get('description') or payload.get('error') or payload.get('message') or ''
                except ValueError:
                    detail = ''

            lowered_context = error_context.lower()
            if status_code == 404 and ('fetch project' in lowered_context or 'fetch mod' in lowered_context):
                message = f"{error_context}: Not found"
            elif detail:
                message = f"{error_context}: {detail}"
            elif status_code is not None:
                message = f"{error_context}: HTTP {status_code}"
            else:
                message = f"{error_context}: {exc}"

            raise ModrinthApiError(message, status_code=status_code) from exc

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
        facets = [["project_type:modpack"]]

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
        clean_install: bool = False,
    ) -> Dict[str, Any]:
        """Download and install a modpack into a server directory."""
        loaders = [loader] if loader else None
        game_versions = [mc_version] if mc_version else None

        versions = self.get_project_versions(
            project_id, loaders=loaders, game_versions=game_versions
        )
        best = self.pick_best_version(versions)

        if not best and loaders:
            versions = self.get_project_versions(
                project_id, loaders=None, game_versions=game_versions
            )
            best = self.pick_best_version(versions)

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
        cleaned_paths: List[str] = []

        if clean_install:
            cleaned_paths = self.clean_modpack_switch_paths(install_path)

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

                for entry in index.get('files', []):
                    env = entry.get('env', {})
                    if env.get('server', 'required') == 'unsupported':
                        files_skipped.append(entry['path'])
                        continue

                    target = (install_path / entry['path']).resolve()
                    if not str(target).startswith(str(install_path)):
                        raise ModrinthApiError(f"Invalid path in modpack index: {entry['path']}")

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

                for member in zf.infolist():
                    if member.is_dir():
                        continue
                    relative: Optional[str] = None
                    matched_prefix: Optional[str] = None
                    for prefix in ('server-overrides/', 'overrides/'):
                        if member.filename.startswith(prefix):
                            relative = member.filename[len(prefix):]
                            matched_prefix = prefix
                            break
                    if not relative:
                        continue

                    if (
                        matched_prefix == 'overrides/'
                        and relative.startswith('mods/')
                        and relative.lower().endswith('.jar')
                    ):
                        files_skipped.append(member.filename)
                        continue

                    target = (install_path / relative).resolve()
                    if not str(target).startswith(str(install_path)):
                        continue
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(member) as src, open(target, 'wb') as dst:
                        shutil.copyfileobj(src, dst)

        removed_client_mods = self.prune_incompatible_server_mods(install_path)

        return {
            'version': best.get('version_number'),
            'name': best.get('name'),
            'files_installed': len(files_installed),
            'files_skipped': len(files_skipped),
            'clean_install': clean_install,
            'cleaned_paths': cleaned_paths,
            'removed_client_mods': removed_client_mods,
            'dependencies': index.get('dependencies', {}),
        }

    def clean_modpack_switch_paths(self, install_path: Path) -> List[str]:
        """Remove known modpack-managed directories before a clean switch."""
        install_root = Path(install_path).resolve()
        removed: List[str] = []

        for relative in self.MODPACK_SWITCH_PATHS:
            target = (install_root / relative).resolve()
            if not str(target).startswith(str(install_root)):
                continue
            if not target.exists():
                continue

            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()
            removed.append(relative)

        return removed

    def prune_incompatible_server_mods(self, install_path: Path) -> List[str]:
        """Remove mods that are not suitable for dedicated server runtime."""
        mods_dir = (Path(install_path).resolve() / 'mods').resolve()
        if not mods_dir.exists() or not mods_dir.is_dir():
            return []

        removed: List[str] = []
        for jar_path in sorted(mods_dir.glob('*.jar')):
            if not jar_path.is_file():
                continue

            try:
                with zipfile.ZipFile(jar_path) as zf:
                    if 'fabric.mod.json' not in zf.namelist():
                        continue
                    mod_meta = json.loads(zf.read('fabric.mod.json'))
            except (OSError, zipfile.BadZipFile, json.JSONDecodeError):
                continue

            mod_id = str(mod_meta.get('id') or '').strip()
            environment = str(mod_meta.get('environment') or '').strip().lower()
            entrypoints = mod_meta.get('entrypoints') or {}

            should_remove = False
            if mod_id in self.SERVER_BLOCKED_MOD_IDS:
                should_remove = True
            elif environment == 'client':
                should_remove = True
            elif 'client' in entrypoints and 'server' not in entrypoints and 'main' not in entrypoints:
                should_remove = True

            if should_remove:
                try:
                    jar_path.unlink()
                    removed.append(jar_path.name)
                except OSError:
                    continue

        return removed

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
