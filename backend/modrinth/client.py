"""Modrinth API client for fetching mod and modpack information."""

from __future__ import annotations

import json
import shutil
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests


class ModrinthApiError(Exception):
    """Raised when a Modrinth API request fails."""

    def __init__(self, message: str, status_code: int | None = None, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.status_code = status_code
        self.details = details or {}


class ModrinthClient:
    """Client for interacting with the Modrinth API."""

    BASE_URL = "https://api.modrinth.com/v2"
    USER_AGENT = "philderks/Fabricator/1.0.0 (https://github.com/philderks/Fabricator)"
    MODPACK_SWITCH_PATHS = (
        # Replace only pack-managed content, not core server data.
        "mods",
        "config",
        "defaultconfigs",
        "kubejs",
        "scripts",
    )
    PROTECTED_SERVER_PATHS = {
        "world",
        "logs",
        "backups",
        "libraries",
        "versions",
    }
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": self.USER_AGENT,
                "Accept": "application/json",
            }
        )

    def _request(self, method: str, url: str, *, timeout: int = 15, error_context: str, **kwargs) -> requests.Response:
        try:
            response = self.session.request(method, url, timeout=timeout, **kwargs)
            response.raise_for_status()
            return response
        except requests.exceptions.RequestException as exc:
            response = getattr(exc, "response", None)
            status_code = getattr(response, "status_code", None)

            detail = ""
            if response is not None:
                try:
                    payload = response.json()
                    detail = payload.get("description") or payload.get("error") or payload.get("message") or ""
                except ValueError:
                    detail = ""

            lowered_context = error_context.lower()
            if status_code == 404 and ("fetch project" in lowered_context or "fetch mod" in lowered_context):
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
        query: str = "",
        mc_version: Optional[str] = None,
        loader: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
        index: str = "downloads",
    ) -> Dict[str, Any]:
        facets: List[List[str]] = [["project_type:mod"]]
        if mc_version:
            facets.append([f"versions:{mc_version}"])
        if loader:
            facets.append([f"categories:{loader}"])

        params = {
            "query": query,
            "limit": max(1, min(limit, 100)),
            "offset": max(0, offset),
            "index": index,
            "facets": json.dumps(facets),
        }

        response = self._request(
            "get",
            f"{self.BASE_URL}/search",
            params=params,
            timeout=15,
            error_context="Failed to search mods",
        )
        return response.json()

    def search_modpacks(
        self,
        query: str = "",
        mc_version: Optional[str] = None,
        loader: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
        index: str = "downloads",
    ) -> Dict[str, Any]:
        facets: List[List[str]] = [["project_type:modpack"]]
        if mc_version:
            facets.append([f"versions:{mc_version}"])
        if loader:
            facets.append([f"categories:{loader}"])

        params = {
            "query": query,
            "limit": max(1, min(limit, 100)),
            "offset": max(0, offset),
            "index": index,
            "facets": json.dumps(facets),
        }

        response = self._request(
            "get",
            f"{self.BASE_URL}/search",
            params=params,
            timeout=15,
            error_context="Failed to search modpacks",
        )
        return response.json()

    def get_mod(self, mod_id: str) -> Dict[str, Any]:
        response = self._request(
            "get",
            f"{self.BASE_URL}/project/{mod_id}",
            timeout=15,
            error_context="Failed to fetch mod",
        )
        return response.json()

    def get_project(self, project_id: str) -> Dict[str, Any]:
        response = self._request(
            "get",
            f"{self.BASE_URL}/project/{project_id}",
            timeout=15,
            error_context="Failed to fetch project",
        )
        return response.json()

    def get_mod_versions(
        self,
        mod_id: str,
        loaders: Optional[List[str]] = None,
        game_versions: Optional[List[str]] = None,
        featured: Optional[bool] = None,
    ) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {}
        if loaders:
            params["loaders"] = json.dumps(loaders)
        if game_versions:
            params["game_versions"] = json.dumps(game_versions)
        if featured is not None:
            params["featured"] = str(featured).lower()

        response = self._request(
            "get",
            f"{self.BASE_URL}/project/{mod_id}/version",
            params=params if params else None,
            timeout=15,
            error_context="Failed to fetch mod versions",
        )
        return response.json()

    def get_project_versions(
        self,
        project_id: str,
        loaders: Optional[List[str]] = None,
        game_versions: Optional[List[str]] = None,
        featured: Optional[bool] = None,
    ) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {}
        if loaders:
            params["loaders"] = json.dumps(loaders)
        if game_versions:
            params["game_versions"] = json.dumps(game_versions)
        if featured is not None:
            params["featured"] = str(featured).lower()

        response = self._request(
            "get",
            f"{self.BASE_URL}/project/{project_id}/version",
            params=params if params else None,
            timeout=15,
            error_context="Failed to fetch project versions",
        )
        return response.json()

    def get_version(self, version_id: str) -> Dict[str, Any]:
        response = self._request(
            "get",
            f"{self.BASE_URL}/version/{version_id}",
            timeout=15,
            error_context="Failed to fetch version",
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

    def get_mod_download_url(self, mod_id: str, mc_version: str, loader: str = "fabric") -> Optional[str]:
        versions = self.get_mod_versions(mod_id=mod_id, loaders=[loader], game_versions=[mc_version])

        best_version = self.pick_best_version(versions)
        if not best_version:
            return None

        return self.get_primary_file_url(best_version)

    def resolve_project_version(
        self,
        project_id: str,
        mc_version: Optional[str] = None,
        loader: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        loaders = [loader] if loader else None
        game_versions = [mc_version] if mc_version else None

        versions = self.get_project_versions(project_id=project_id, loaders=loaders, game_versions=game_versions)
        best_version = self.pick_best_version(versions)
        if not best_version:
            return None

        return {
            "version": best_version,
            "download_url": self.get_primary_file_url(best_version),
        }

    def download_mod(self, download_url: str, target_folder: Path) -> Optional[Path]:
        try:
            target_folder.mkdir(parents=True, exist_ok=True)
            filename = download_url.split("/")[-1]
            target_path = target_folder / filename

            with self._request(
                "get",
                download_url,
                stream=True,
                timeout=60,
                error_context="Failed to download mod file",
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
        allow_missing: bool = False,
        mod_side_overrides: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Download and install a modpack into a server directory.

        Downloads the .mrpack file, installs all server-side files listed in
        modrinth.index.json, and extracts overrides/ and server-overrides/ into
        the server root.
        """
        loaders = [loader] if loader else None
        game_versions = [mc_version] if mc_version else None

        versions = self.get_project_versions(project_id, loaders=loaders, game_versions=game_versions)
        best = self.pick_best_version(versions)

        if not best and loaders:
            versions = self.get_project_versions(project_id, loaders=None, game_versions=game_versions)
            best = self.pick_best_version(versions)

        if not best and (loaders or game_versions):
            versions = self.get_project_versions(project_id)
            best = self.pick_best_version(versions)

        if not best:
            raise ModrinthApiError("No suitable modpack version found")

        version_game_versions = best.get("game_versions") or []
        if mc_version and version_game_versions and mc_version not in version_game_versions:
            raise ModrinthApiError(
                (
                    f"Selected server version {mc_version} is not compatible with this modpack version "
                    f"({', '.join(version_game_versions)})."
                ),
                status_code=409,
                details={
                    "requested_mc_version": mc_version,
                    "modpack_game_versions": version_game_versions,
                },
            )

        version_loaders = [str(value).lower() for value in (best.get("loaders") or [])]
        if loader and version_loaders and loader.lower() not in version_loaders:
            raise ModrinthApiError(
                (
                    f"Selected loader {loader} is not compatible with this modpack version "
                    f"({', '.join(version_loaders)})."
                ),
                status_code=409,
                details={
                    "requested_loader": loader.lower(),
                    "modpack_loaders": version_loaders,
                },
            )

        download_url = self.get_primary_file_url(best)
        if not download_url:
            raise ModrinthApiError("No download URL found for modpack version")

        install_path = Path(install_path).resolve()
        files_installed: List[str] = []
        files_skipped: List[str] = []
        missing_files: List[Dict[str, str]] = []
        uncertain_mod_files: List[Dict[str, str]] = []
        index: Dict[str, Any] = {}
        cleaned_paths: List[str] = []
        normalized_overrides = self._normalize_mod_side_overrides(mod_side_overrides)

        if clean_install:
            cleaned_paths = self.clean_modpack_switch_paths(install_path)

        with tempfile.TemporaryDirectory() as tmp_dir:
            mrpack_path = Path(tmp_dir) / "modpack.mrpack"

            with self._request(
                "get",
                download_url,
                stream=True,
                timeout=120,
                error_context="Failed to download modpack",
            ) as response:
                with open(mrpack_path, "wb") as fh:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            fh.write(chunk)

            with zipfile.ZipFile(mrpack_path, "r") as zf:
                with zf.open("modrinth.index.json") as fh:
                    index = json.loads(fh.read())

                if not allow_missing:
                    precheck_missing = self._collect_unavailable_modpack_entries(
                        index.get("files", []),
                        normalized_overrides,
                    )
                    if precheck_missing:
                        raise ModrinthApiError(
                            "Some modpack files could not be downloaded",
                            status_code=409,
                            details={
                                "missing_files": precheck_missing,
                                "can_continue_with_missing": True,
                            },
                        )

                for entry in index.get("files", []):
                    env = entry.get("env", {})
                    if env.get("server", "required") == "unsupported":
                        files_skipped.append(entry.get("path", "<unknown>"))
                        continue

                    entry_path = entry.get("path")
                    if not entry_path:
                        files_skipped.append("<unknown>")
                        continue

                    if entry_path.lower().startswith("mods/") and entry_path.lower().endswith(".jar"):
                        decision, reason = self._resolve_index_mod_side(entry_path, env, normalized_overrides)
                        if decision == "client":
                            files_skipped.append(entry_path)
                            continue

                    target = (install_path / entry_path).resolve()
                    if not str(target).startswith(str(install_path)):
                        raise ModrinthApiError(f"Invalid path in modpack index: {entry_path}")

                    target.parent.mkdir(parents=True, exist_ok=True)
                    downloads = entry.get("downloads", [])
                    if not downloads:
                        missing_files.append(
                            {
                                "path": entry_path,
                                "reason": "No download URL in modpack index",
                            }
                        )
                        files_skipped.append(entry_path)
                        if allow_missing:
                            continue
                        raise ModrinthApiError(
                            "Some modpack files could not be downloaded",
                            status_code=409,
                            details={
                                "missing_files": missing_files,
                                "can_continue_with_missing": True,
                            },
                        )

                    try:
                        with self._request(
                            "get",
                            downloads[0],
                            stream=True,
                            timeout=60,
                            error_context=f"Failed to download {entry_path}",
                        ) as r:
                            with open(target, "wb") as fh:
                                for chunk in r.iter_content(chunk_size=8192):
                                    if chunk:
                                        fh.write(chunk)

                        if entry_path.lower().startswith("mods/") and entry_path.lower().endswith(".jar"):
                            forced_side = normalized_overrides.get(entry_path)
                            classification, class_reason = self._classify_mod_jar_for_server(target)

                            if forced_side == "client":
                                try:
                                    target.unlink()
                                except OSError:
                                    pass
                                files_skipped.append(entry_path)
                                continue

                            if forced_side == "server":
                                files_installed.append(entry_path)
                                continue

                            if classification == "client":
                                try:
                                    target.unlink()
                                except OSError:
                                    pass
                                files_skipped.append(entry_path)
                                continue

                            if classification == "uncertain":
                                try:
                                    target.unlink()
                                except OSError:
                                    pass
                                uncertain_mod_files.append(
                                    {
                                        "path": entry_path,
                                        "reason": class_reason or "Unable to detect dedicated-server compatibility from mod metadata",
                                    }
                                )
                                continue

                        files_installed.append(entry_path)
                    except ModrinthApiError as exc:
                        missing_files.append(
                            {
                                "path": entry_path,
                                "reason": str(exc),
                            }
                        )
                        files_skipped.append(entry_path)
                        if allow_missing:
                            continue
                        raise ModrinthApiError(
                            "Some modpack files could not be downloaded",
                            status_code=409,
                            details={
                                "missing_files": missing_files,
                                "can_continue_with_missing": True,
                            },
                        ) from exc

                for member in zf.infolist():
                    if member.is_dir():
                        continue

                    relative: Optional[str] = None
                    for prefix in ("server-overrides/", "overrides/"):
                        if member.filename.startswith(prefix):
                            relative = member.filename[len(prefix):]
                            break
                    if not relative:
                        continue

                    target = (install_path / relative).resolve()
                    if not str(target).startswith(str(install_path)):
                        continue
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(member) as src, open(target, "wb") as dst:
                        shutil.copyfileobj(src, dst)

                    if relative.lower().startswith("mods/") and relative.lower().endswith(".jar"):
                        scoped_path = f"{prefix}{relative}"
                        forced_side = normalized_overrides.get(scoped_path) or normalized_overrides.get(relative)
                        classification, reason = self._classify_mod_jar_for_server(target)

                        if forced_side == "client":
                            try:
                                target.unlink()
                            except OSError:
                                pass
                            files_skipped.append(scoped_path)
                            continue

                        if classification == "client":
                            try:
                                target.unlink()
                            except OSError:
                                pass
                            files_skipped.append(scoped_path)
                            continue

                        if classification == "uncertain" and forced_side != "server":
                            try:
                                target.unlink()
                            except OSError:
                                pass
                            uncertain_mod_files.append({
                                "path": scoped_path,
                                "reason": reason or "Unable to detect dedicated-server compatibility from mod metadata",
                            })
                            continue

        if uncertain_mod_files:
            raise ModrinthApiError(
                "Some mods could not be classified as client or server",
                status_code=409,
                details={
                    "uncertain_mod_files": uncertain_mod_files,
                    "can_continue_with_uncertain": True,
                },
            )

        return {
            "version": best.get("version_number"),
            "name": best.get("name"),
            "files_installed": len(files_installed),
            "files_skipped": len(files_skipped),
            "clean_install": clean_install,
            "cleaned_paths": cleaned_paths,
            "missing_files": missing_files,
            "allow_missing": allow_missing,
            "dependencies": index.get("dependencies", {}),
            "uncertain_mod_files": uncertain_mod_files,
        }

    def _collect_unavailable_modpack_entries(
        self,
        entries: List[Dict[str, Any]],
        mod_side_overrides: Optional[Dict[str, str]] = None,
    ) -> List[Dict[str, str]]:
        missing: List[Dict[str, str]] = []
        overrides = mod_side_overrides or {}
        for entry in entries:
            env = entry.get("env", {})
            if env.get("server", "required") == "unsupported":
                continue

            path = entry.get("path") or "<unknown>"
            if path.lower().startswith("mods/") and path.lower().endswith(".jar"):
                decision, _reason = self._resolve_index_mod_side(path, env, overrides)
                if decision != "server":
                    continue

            downloads = entry.get("downloads", [])
            if not downloads:
                missing.append({"path": path, "reason": "No download URL in modpack index"})
                continue

            error = self._probe_download_url(downloads[0])
            if error:
                missing.append({"path": path, "reason": error})

        return missing

    def _probe_download_url(self, url: str) -> str:
        try:
            with self.session.get(url, stream=True, timeout=20) as response:
                response.raise_for_status()
            return ""
        except requests.exceptions.RequestException as exc:
            response = getattr(exc, "response", None)
            status_code = getattr(response, "status_code", None)
            if status_code is not None:
                return f"Download URL returned HTTP {status_code}"
            return f"Download failed: {exc}"

    def _normalize_mod_side_overrides(self, mod_side_overrides: Optional[Dict[str, str]]) -> Dict[str, str]:
        if not isinstance(mod_side_overrides, dict):
            return {}

        normalized: Dict[str, str] = {}
        for raw_path, raw_side in mod_side_overrides.items():
            path = str(raw_path or "").strip()
            side = str(raw_side or "").strip().lower()
            if not path:
                continue
            if side not in ("client", "server"):
                continue
            normalized[path] = side
        return normalized

    def _resolve_index_mod_side(
        self,
        entry_path: str,
        env: Dict[str, Any],
        mod_side_overrides: Dict[str, str],
    ) -> Tuple[str, str]:
        forced_side = mod_side_overrides.get(entry_path)
        if forced_side in ("client", "server"):
            return forced_side, "User override"

        server_env = str(env.get("server") or "").strip().lower()
        if server_env == "unsupported":
            return "client", "Index env marks server as unsupported"
        if server_env in ("required", "optional"):
            return "server", "Index env allows server"

        return "uncertain", "No server env metadata in modpack index"

    def _classify_mod_jar_for_server(self, jar_path: Path) -> Tuple[str, str]:
        try:
            with zipfile.ZipFile(jar_path) as zf:
                if "fabric.mod.json" not in zf.namelist():
                    return "uncertain", "fabric.mod.json missing"
                mod_meta = json.loads(zf.read("fabric.mod.json"))
        except (OSError, zipfile.BadZipFile, json.JSONDecodeError):
            return "uncertain", "Failed to parse mod metadata"

        environment = str(mod_meta.get("environment") or "").strip().lower()
        entrypoints = mod_meta.get("entrypoints") or {}

        if environment == "client":
            return "client", "environment=client"
        if environment == "server":
            return "server", "environment=server"
        if "client" in entrypoints and "server" not in entrypoints and "main" not in entrypoints:
            return "client", "Only client entrypoint declared"
        if "server" in entrypoints and "client" not in entrypoints:
            return "server", "Server entrypoint declared"

        return "uncertain", "Metadata does not clearly mark client/server"

    def clean_modpack_switch_paths(self, install_path: Path) -> List[str]:
        """Remove known modpack-managed directories before a clean switch."""
        install_root = Path(install_path).resolve()
        removed: List[str] = []

        for relative in self.MODPACK_SWITCH_PATHS:
            if relative in self.PROTECTED_SERVER_PATHS:
                continue

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

    def get_categories(self) -> List[Dict[str, Any]]:
        response = self._request(
            "get",
            f"{self.BASE_URL}/tag/category",
            timeout=15,
            error_context="Failed to fetch categories",
        )
        return response.json()

    def get_loaders(self) -> List[Dict[str, Any]]:
        response = self._request(
            "get",
            f"{self.BASE_URL}/tag/loader",
            timeout=15,
            error_context="Failed to fetch loaders",
        )
        return response.json()

    def get_game_versions(self) -> List[Dict[str, Any]]:
        response = self._request(
            "get",
            f"{self.BASE_URL}/tag/game_version",
            timeout=15,
            error_context="Failed to fetch game versions",
        )
        return response.json()
