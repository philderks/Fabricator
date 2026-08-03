"""Modrinth API client for fetching mod and modpack information."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import sys
import tempfile
import zipfile

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

from backend.modrinth.ratelimit import RateLimitExceeded, shared_limiter
from backend.utils.zip import is_within


def _retry_after_seconds(response: Optional[requests.Response]) -> Optional[float]:
    """Parse a ``Retry-After`` header (seconds form), or None.

    Modrinth sends the integer-seconds form. The HTTP-date form is not parsed:
    treating it as absent falls back to the limiter's own default cooldown,
    which is safe, whereas mis-parsing it could pause for hours.
    """
    if response is None:
        return None
    raw = response.headers.get("Retry-After")
    if raw is None:
        return None
    try:
        return max(0.0, float(str(raw).strip()))
    except (TypeError, ValueError):
        return None


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
    CLIENT_ONLY_PREFIXES = (
        "resourcepacks/", "shaderpacks/",
        "config/iris/", "config/oculus/", "config/optifine/",
    )
    # Client-only Java package prefixes (slash-form, as they appear in .class
    # constant pools). A class file that imports any of these will crash on a
    # dedicated server at classloading. Used as a fallback when a Forge mod's
    # mods.toml is silent on side — the common case for ETF, ModernUI,
    # Dynamic FPS, etc.
    CLIENT_ONLY_CLASS_PATTERNS: tuple[bytes, ...] = (
        b"org/lwjgl/glfw/",
        b"com/mojang/blaze3d/",
        b"net/minecraft/client/gui/",
        b"net/minecraft/client/renderer/",
    )

    # Modrinth caps a single bulk lookup implicitly (URL length for GET, body
    # size for POST) rather than by a documented count. 200 keeps a
    # `projects?ids=[...]` query string well inside any proxy's URL limit and
    # keeps one slow request from stalling a whole mods folder.
    BULK_CHUNK_SIZE = 200

    def __init__(self, limiter=None):
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": self.USER_AGENT,
                "Accept": "application/json",
            }
        )
        # Defaults to the process-wide bucket; the parameter exists so tests can
        # supply an isolated one instead of leaking spent tokens between cases.
        self.limiter = limiter if limiter is not None else shared_limiter

    def _request(self, method: str, url: str, *, timeout: int = 15, error_context: str, **kwargs) -> requests.Response:
        # Every call spends from the process-wide budget before it goes out.
        # Modrinth's limit is per-IP, so this is the only place that can keep
        # the deployment inside it (issue #52).
        try:
            self.limiter.acquire()
        except RateLimitExceeded as exc:
            raise ModrinthApiError(
                f"{error_context}: too many Modrinth requests, please retry shortly",
                status_code=429,
                details={"retry_after": round(exc.retry_after, 1)},
            ) from exc

        try:
            response = self.session.request(method, url, timeout=timeout, **kwargs)
            self.limiter.observe(response.headers)
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

            # The API says we overspent. Park every caller for as long as it
            # asks, and pass Retry-After on so the frontend's backoff stops
            # having to guess (it reads `retry_after` off the error body).
            details: Dict[str, Any] = {}
            if status_code == 429:
                cooldown = self.limiter.penalize(_retry_after_seconds(response))
                details["retry_after"] = round(cooldown, 1)

            lowered_context = error_context.lower()
            if status_code == 404 and "fetch project" in lowered_context:
                message = f"{error_context}: Not found"
            elif detail:
                message = f"{error_context}: {detail}"
            elif status_code is not None:
                message = f"{error_context}: HTTP {status_code}"
            else:
                message = f"{error_context}: {exc}"

            raise ModrinthApiError(message, status_code=status_code, details=details) from exc

    def _json(self, response: requests.Response, error_context: str) -> Any:
        """Parse a success response body as JSON, mapping a non-JSON body to a
        clean ModrinthApiError.

        ``_request`` only guards ``.json()`` on the *error* path. A 200 can
        still carry HTML (a captive portal, a WAF interstitial, a proxy error
        page), where a raw ``JSONDecodeError`` would otherwise surface as a 500
        instead of the client's normal ``ModrinthApiError`` shape.
        """
        try:
            return response.json()
        except ValueError as exc:
            raise ModrinthApiError(
                f"{error_context}: unexpected non-JSON response from Modrinth",
                status_code=502,
            ) from exc

    def search(
        self,
        project_type: str,
        query: str = "",
        mc_version: Optional[str] = None,
        loader: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
        index: str = "downloads",
    ) -> Dict[str, Any]:
        """Search Modrinth for projects of the given type.

        ``project_type`` is the Modrinth ``project_type`` facet value
        (e.g. ``"mod"``, ``"modpack"``).
        """
        facets: List[List[str]] = [[f"project_type:{project_type}"]]
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
            error_context=f"Failed to search {project_type}s",
        )
        return self._json(response, f"Failed to search {project_type}s")

    def get_project(self, project_id: str) -> Dict[str, Any]:
        """Fetch a Modrinth project (mod, modpack, resource pack, etc.)."""
        response = self._request(
            "get",
            f"{self.BASE_URL}/project/{project_id}",
            timeout=15,
            error_context="Failed to fetch project",
        )
        return self._json(response, "Failed to fetch project")

    def get_versions_by_hashes(
        self, hashes: List[str], algorithm: str = "sha1"
    ) -> Dict[str, Dict[str, Any]]:
        """Look a batch of file hashes up against Modrinth.

        ``POST /v2/version_files`` returns a ``{hash: version}`` map, omitting
        hashes Modrinth has never seen. This is the endpoint the mods page is
        supposed to use: one request identifies a whole folder exactly, where
        guessing project slugs from filenames cost ~3.6 requests per jar and
        still mis-identified anything not named after its slug (issue #52).
        """
        unique = list(dict.fromkeys(h.lower() for h in hashes if h))
        if not unique:
            return {}

        resolved: Dict[str, Dict[str, Any]] = {}
        for start in range(0, len(unique), self.BULK_CHUNK_SIZE):
            chunk = unique[start:start + self.BULK_CHUNK_SIZE]
            response = self._request(
                "post",
                f"{self.BASE_URL}/version_files",
                json={"hashes": chunk, "algorithm": algorithm},
                timeout=30,
                error_context="Failed to look up files",
            )
            payload = self._json(response, "Failed to look up files")
            if isinstance(payload, dict):
                resolved.update(payload)
        return resolved

    def get_projects(self, project_ids: List[str]) -> List[Dict[str, Any]]:
        """Fetch several projects in one request (``GET /v2/projects?ids=``).

        Unknown ids are omitted rather than erroring, so callers must key the
        result by id instead of assuming positional correspondence.
        """
        unique = list(dict.fromkeys(pid for pid in project_ids if pid))
        if not unique:
            return []

        projects: List[Dict[str, Any]] = []
        for start in range(0, len(unique), self.BULK_CHUNK_SIZE):
            chunk = unique[start:start + self.BULK_CHUNK_SIZE]
            response = self._request(
                "get",
                f"{self.BASE_URL}/projects",
                params={"ids": json.dumps(chunk)},
                timeout=30,
                error_context="Failed to fetch projects",
            )
            payload = self._json(response, "Failed to fetch projects")
            if isinstance(payload, list):
                projects.extend(item for item in payload if isinstance(item, dict))
        return projects

    def get_project_versions(
        self,
        project_id: str,
        loaders: Optional[List[str]] = None,
        game_versions: Optional[List[str]] = None,
        featured: Optional[bool] = None,
    ) -> List[Dict[str, Any]]:
        """Fetch versions for a Modrinth project."""
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
        return self._json(response, "Failed to fetch project versions")

    def get_version(self, version_id: str) -> Dict[str, Any]:
        response = self._request(
            "get",
            f"{self.BASE_URL}/version/{version_id}",
            timeout=15,
            error_context="Failed to fetch version",
        )
        return self._json(response, "Failed to fetch version")

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

    def get_project_download_url(
        self,
        project_id: str,
        mc_version: str,
        loader: str = "fabric",
        loaders: Optional[List[str]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Resolve the best download for a project at ``mc_version``.

        ``loaders`` (a list) takes precedence over the single ``loader`` when
        provided — used for plugin servers, where the accepted loader facets
        are a compatibility chain (e.g. Paper accepts ``paper``/``spigot``/
        ``bukkit``-tagged plugins). Falls back to ``[loader]`` for the classic
        single-loader mod case.
        """
        loader_facets = loaders if loaders else [loader]
        versions = self.get_project_versions(
            project_id=project_id, loaders=loader_facets, game_versions=[mc_version]
        )
        best_version = self.pick_best_version(versions)
        if not best_version:
            return None

        url = self.get_primary_file_url(best_version)
        if not url:
            return None

        hashes: Dict[str, str] = {}
        for f in best_version.get("files", []):
            if f.get("url") == url:
                hashes = f.get("hashes") or {}
                break

        # version_id/version_number ride along so the install route can record
        # which release landed on disk without re-resolving.
        return {
            "url": url,
            "hashes": hashes,
            "version_id": best_version.get("id"),
            "version_number": best_version.get("version_number"),
        }

    def get_pinned_download(
        self, project_id: str, version_id: str
    ) -> Optional[Dict[str, Any]]:
        """Resolve the download for one explicitly chosen version.

        The counterpart to :meth:`get_project_download_url`, which picks the
        newest release itself. Here the caller has named a version, so no
        selection happens — but the version is checked to actually belong to
        ``project_id`` first. Without that, a caller could pass any version id
        and install a completely different mod under this project's name, and
        the install manifest would record the lie (#56).

        ``project_id`` may be a slug, so the check compares against both it and
        the project's canonical id. Returns None when the version has no
        downloadable primary file; raises ModrinthApiError for unknown ids.
        """
        version = self.get_version(version_id)
        owner = str(version.get("project_id") or "")

        if owner.lower() != str(project_id).lower():
            # Slug was passed — resolve it before declaring a mismatch.
            project = self.get_project(project_id)
            if owner != str(project.get("id") or ""):
                raise ModrinthApiError(
                    f"Version {version_id} does not belong to {project_id}",
                    status_code=400,
                )

        url = self.get_primary_file_url(version)
        if not url:
            return None

        hashes: Dict[str, str] = {}
        for f in version.get("files", []):
            if f.get("url") == url:
                hashes = f.get("hashes") or {}
                break

        return {
            "url": url,
            "hashes": hashes,
            "version_id": version.get("id"),
            "version_number": version.get("version_number"),
        }

    def resolve_project_version(
        self,
        project_id: str,
        mc_version: Optional[str] = None,
        loader: Optional[str] = None,
        loaders: Optional[List[str]] = None,
    ) -> Optional[Dict[str, Any]]:
        # ``loaders`` (a list) takes precedence over the single ``loader`` — used
        # for plugin servers, whose accepted facets are a compatibility chain
        # (paper/spigot/bukkit). Falls back to ``[loader]`` for mods.
        loader_facets = loaders if loaders else ([loader] if loader else None)
        game_versions = [mc_version] if mc_version else None

        versions = self.get_project_versions(project_id=project_id, loaders=loader_facets, game_versions=game_versions)
        best_version = self.pick_best_version(versions)
        if not best_version:
            return None

        return {
            "version": best_version,
            "download_url": self.get_primary_file_url(best_version),
        }

    _FILENAME_RE = re.compile(r"^[A-Za-z0-9._+\- ]+$")

    def download_mod(
        self,
        download_url: str,
        target_folder: Path,
        hashes: Optional[Dict[str, str]] = None,
    ) -> Optional[Path]:
        """Download a mod file into ``target_folder`` with path + hash checks.

        - Filename is derived from the last URL path segment and must match
          a strict safe-character regex; traversal attempts raise
          ModrinthApiError.
        - When ``hashes`` is provided, sha1/sha512 are verified; a mismatch
          deletes the partial file and raises.
        """
        from urllib.parse import urlparse, unquote

        parsed = urlparse(download_url)
        # Reject any URL whose path contains a dot-dot segment (traversal attempt).
        path_segments = parsed.path.split("/")
        if ".." in path_segments or "." in path_segments:
            raise ModrinthApiError(
                f"Refusing to save mod: URL path contains traversal segments: {parsed.path!r}"
            )
        last_segment = unquote(parsed.path.rsplit("/", 1)[-1])
        filename = last_segment.strip()

        if not filename or not self._FILENAME_RE.match(filename):
            raise ModrinthApiError(
                f"Refusing to save mod: unsafe filename derived from URL: {last_segment!r}"
            )

        try:
            target_folder = Path(target_folder).resolve()
            target_folder.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise ModrinthApiError(f"Failed to prepare mods folder: {exc}") from exc

        target_path = (target_folder / filename).resolve()
        try:
            target_path.relative_to(target_folder)
        except ValueError:
            raise ModrinthApiError(
                f"Refusing to save mod: resolved path escapes mods folder: {target_path}"
            )

        sha1 = hashlib.sha1() if hashes and hashes.get("sha1") else None
        sha512 = hashlib.sha512() if hashes and hashes.get("sha512") else None

        try:
            with self._request(
                "get",
                download_url,
                stream=True,
                timeout=60,
                error_context="Failed to download mod file",
            ) as response:
                with open(target_path, "wb") as file_handle:
                    for chunk in response.iter_content(chunk_size=8192):
                        if not chunk:
                            continue
                        file_handle.write(chunk)
                        if sha1 is not None:
                            sha1.update(chunk)
                        if sha512 is not None:
                            sha512.update(chunk)
        except OSError as exc:
            try:
                target_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise ModrinthApiError(f"Failed to save mod file: {exc}") from exc

        if sha512 is not None and sha512.hexdigest() != hashes["sha512"].lower():
            target_path.unlink(missing_ok=True)
            raise ModrinthApiError(f"Mod download SHA-512 mismatch for {filename}")
        if sha1 is not None and sha1.hexdigest() != hashes["sha1"].lower():
            target_path.unlink(missing_ok=True)
            raise ModrinthApiError(f"Mod download SHA-1 mismatch for {filename}")

        return target_path

    def install_modpack(
        self,
        project_id: str,
        install_path: Path,
        mc_version: Optional[str] = None,
        loader: Optional[str] = None,
        clean_install: bool = False,
        allow_missing: bool = False,
        mod_side_overrides: Optional[Dict[str, str]] = None,
        progress_callback: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Download a modpack from Modrinth and install it into a server dir.

        Resolves the best version for ``mc_version``/``loader``, downloads its
        .mrpack, then hands off to :meth:`install_mrpack_archive` — which is
        the same code path an uploaded pack takes (#53). Upstream project and
        version identity is layered on afterwards, since only a pack fetched
        from Modrinth has any.
        """
        def _report(stage: str, current: int = 0, total: int = 0, detail: str = ""):
            if progress_callback:
                progress_callback(stage=stage, current=current, total=total, detail=detail)

        _report("resolving")
        project_details = self.get_project(project_id)
        project_title = project_details.get("title", project_id)

        best = self._resolve_modpack_version(project_id, mc_version, loader)
        download_url = self.get_primary_file_url(best)
        if not download_url:
            raise ModrinthApiError("No download URL found for modpack version")

        _report("downloading_pack")
        with tempfile.TemporaryDirectory() as tmp_dir:
            mrpack_path = self._download_mrpack(download_url, Path(tmp_dir))
            result = self.install_mrpack_archive(
                mrpack_path,
                install_path,
                loader=loader,
                clean_install=clean_install,
                allow_missing=allow_missing,
                mod_side_overrides=mod_side_overrides,
                progress_callback=progress_callback,
            )

        result.update({
            "version": best.get("version_number"),
            "name": project_title,
            "version_name": best.get("name"),
            "mc_version": (best.get("game_versions") or [None])[0],
            "loaders": best.get("loaders", []),
            "project_id": project_id,
            "version_id": best.get("id"),
        })
        return result

    def install_mrpack_archive(
        self,
        mrpack_path: Path,
        install_path: Path,
        loader: Optional[str] = None,
        clean_install: bool = False,
        allow_missing: bool = False,
        mod_side_overrides: Optional[Dict[str, str]] = None,
        progress_callback: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Install an on-disk .mrpack into a server directory.

        Installs every server-side file listed in modrinth.index.json and
        extracts overrides/ and server-overrides/ into the server root. The
        archive is only read, never consumed, so a caller can re-run the
        install after the user resolves missing files or uncertain mod sides.

        Pack identity in the returned dict comes from the index (``name``,
        ``versionId``, ``dependencies``); a caller that knows better — the
        Modrinth download path — overwrites it.
        """
        def _report(stage: str, current: int = 0, total: int = 0, detail: str = ""):
            if progress_callback:
                progress_callback(stage=stage, current=current, total=total, detail=detail)

        install_path = Path(install_path).resolve()
        normalized_overrides = self._normalize_mod_side_overrides(mod_side_overrides)
        cleaned_paths: List[str] = []

        with zipfile.ZipFile(mrpack_path, "r") as zf:
            with zf.open("modrinth.index.json") as fh:
                index = json.loads(fh.read())

            if not allow_missing:
                _report("checking_availability")
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

            # Cleaning happens only once the pack has been read and its files
            # are known to be reachable: an install that fails at the first
            # download should leave the server's mods/ as it found them.
            if clean_install:
                _report("cleaning")
                cleaned_paths = self.clean_modpack_switch_paths(install_path)

            result = self._install_index_files(
                index.get("files", []),
                install_path,
                normalized_overrides,
                allow_missing,
                progress_callback=_report,
                loader=loader,
            )
            _report("extracting_overrides")
            self._extract_overrides(
                zf, install_path, normalized_overrides,
                result["files_installed"],
                result["files_skipped"],
                result["uncertain_mod_files"],
                loader=loader,
            )

        if result["uncertain_mod_files"]:
            raise ModrinthApiError(
                "Some mods could not be classified as client or server",
                status_code=409,
                details={
                    "uncertain_mod_files": result["uncertain_mod_files"],
                    "can_continue_with_uncertain": True,
                },
            )

        dependencies = index.get("dependencies") or {}
        return {
            "version": index.get("versionId"),
            "name": index.get("name"),
            "version_name": index.get("versionId"),
            "mc_version": dependencies.get("minecraft"),
            "loaders": [loader] if loader else [],
            "project_id": None,
            "version_id": None,
            "files_installed": result["files_installed"],
            "files_skipped": result["files_skipped"],
            "clean_install": clean_install,
            "cleaned_paths": cleaned_paths,
            "missing_files": result["missing_files"],
            "allow_missing": allow_missing,
            "dependencies": dependencies,
            "uncertain_mod_files": result["uncertain_mod_files"],
        }

    def _resolve_modpack_version(
        self,
        project_id: str,
        mc_version: Optional[str],
        loader: Optional[str],
    ) -> Dict[str, Any]:
        """Find the best modpack version, with progressive fallbacks."""
        loaders = [loader] if loader else None
        game_versions = [mc_version] if mc_version else None

        best = self.pick_best_version(
            self.get_project_versions(project_id, loaders=loaders, game_versions=game_versions)
        )
        if not best and loaders:
            best = self.pick_best_version(
                self.get_project_versions(project_id, loaders=None, game_versions=game_versions)
            )
        if not best and (loaders or game_versions):
            best = self.pick_best_version(self.get_project_versions(project_id))
        if not best:
            raise ModrinthApiError("No suitable modpack version found")

        version_game_versions = best.get("game_versions") or []
        if mc_version and version_game_versions and mc_version not in version_game_versions:
            raise ModrinthApiError(
                f"This modpack's latest version targets Minecraft {', '.join(version_game_versions)}, "
                f"but your server runs Minecraft {mc_version}. "
                f"Pick a different modpack, or recreate the server with a compatible Minecraft version.",
                status_code=409,
                details={
                    "requested_mc_version": mc_version,
                    "modpack_game_versions": version_game_versions,
                },
            )

        version_loaders = [str(v).lower() for v in (best.get("loaders") or [])]
        if loader and version_loaders and loader.lower() not in version_loaders:
            raise ModrinthApiError(
                f"This modpack's latest version targets {', '.join(version_loaders)}, "
                f"but your server uses {loader}. "
                f"Pick a different modpack, or recreate the server with a compatible loader.",
                status_code=409,
                details={
                    "requested_loader": loader.lower(),
                    "modpack_loaders": version_loaders,
                },
            )

        return best

    def _download_mrpack(self, download_url: str, tmp_dir: Path) -> Path:
        """Download the .mrpack archive to a temporary directory."""
        mrpack_path = tmp_dir / "modpack.mrpack"
        with self._request(
            "get", download_url, stream=True, timeout=120,
            error_context="Failed to download modpack",
        ) as response:
            with open(mrpack_path, "wb") as fh:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        fh.write(chunk)
        return mrpack_path

    def _download_and_verify(
        self,
        url: str,
        target: Path,
        hashes: Optional[Dict[str, str]],
        error_context: str,
    ) -> None:
        """Download a file and verify its hash against the index entry."""
        sha1 = hashlib.sha1()
        sha512 = hashlib.sha512()

        with self._request(
            "get", url, stream=True, timeout=60,
            error_context=error_context,
        ) as r:
            with open(target, "wb") as fh:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        fh.write(chunk)
                        sha1.update(chunk)
                        sha512.update(chunk)

        if not hashes:
            return

        expected_sha512 = hashes.get("sha512")
        if expected_sha512 and sha512.hexdigest() != expected_sha512:
            target.unlink(missing_ok=True)
            raise ModrinthApiError(
                f"{error_context}: SHA-512 mismatch (expected {expected_sha512[:16]}...)",
            )

        expected_sha1 = hashes.get("sha1")
        if expected_sha1 and sha1.hexdigest() != expected_sha1:
            target.unlink(missing_ok=True)
            raise ModrinthApiError(
                f"{error_context}: SHA-1 mismatch (expected {expected_sha1})",
            )

    def _install_index_files(
        self,
        entries: List[Dict[str, Any]],
        install_path: Path,
        overrides: Dict[str, str],
        allow_missing: bool,
        progress_callback: Optional[Any] = None,
        loader: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Download and classify every file listed in the modpack index."""
        files_installed: List[str] = []
        files_skipped: List[str] = []
        missing_files: List[Dict[str, str]] = []
        uncertain_mod_files: List[Dict[str, str]] = []

        server_entries = []
        index_env_decisions: Dict[str, str] = {}
        # NOTE: this loop pre-filters server == "unsupported" before calling
        # ``_resolve_index_mod_side``; that helper relies on this precondition.
        for entry in entries:
            env = entry.get("env", {})
            entry_path = entry.get("path", "")
            if env.get("server", "required") == "unsupported":
                files_skipped.append(entry_path or "<unknown>")
                continue
            if not entry_path:
                files_skipped.append("<unknown>")
                continue
            entry_lower = entry_path.lower()
            if any(entry_lower.startswith(p) for p in self.CLIENT_ONLY_PREFIXES):
                files_skipped.append(entry_path)
                continue
            is_mod_jar = entry_lower.startswith("mods/") and entry_lower.endswith(".jar")
            if is_mod_jar:
                decision, _ = self._resolve_index_mod_side(entry_path, env, overrides)
                if decision == "client":
                    existing = (install_path / entry_path).resolve()
                    if existing.is_file() and is_within(install_path, existing):
                        existing.unlink(missing_ok=True)
                    files_skipped.append(entry_path)
                    continue
                index_env_decisions[entry_path] = decision
            server_entries.append(entry)

        total = len(server_entries)

        for idx, entry in enumerate(server_entries):
            entry_path = entry.get("path")

            if progress_callback:
                progress_callback(stage="installing_files", current=idx + 1, total=total, detail=entry_path)

            is_mod_jar = entry_path.lower().startswith("mods/") and entry_path.lower().endswith(".jar")

            target = (install_path / entry_path).resolve()
            if not is_within(install_path, target):
                raise ModrinthApiError(f"Invalid path in modpack index: {entry_path}")

            target.parent.mkdir(parents=True, exist_ok=True)
            downloads = entry.get("downloads", [])
            if not downloads:
                missing_files.append({"path": entry_path, "reason": "No download URL in modpack index"})
                files_skipped.append(entry_path)
                if allow_missing:
                    continue
                raise ModrinthApiError(
                    "Some modpack files could not be downloaded",
                    status_code=409,
                    details={"missing_files": missing_files, "can_continue_with_missing": True},
                )

            try:
                self._download_and_verify(
                    downloads[0], target,
                    hashes=entry.get("hashes"),
                    error_context=f"Failed to download {entry_path}",
                )
            except ModrinthApiError as exc:
                missing_files.append({"path": entry_path, "reason": str(exc)})
                files_skipped.append(entry_path)
                if allow_missing:
                    continue
                raise ModrinthApiError(
                    "Some modpack files could not be downloaded",
                    status_code=409,
                    details={"missing_files": missing_files, "can_continue_with_missing": True},
                ) from exc

            if is_mod_jar:
                disposition = self._classify_installed_mod(
                    target, entry_path, overrides,
                    files_installed, files_skipped, uncertain_mod_files,
                    index_env_decision=index_env_decisions.get(entry_path, ""),
                    loader=loader,
                )
                if disposition is not None:
                    continue

            files_installed.append(entry_path)

        return {
            "files_installed": files_installed,
            "files_skipped": files_skipped,
            "missing_files": missing_files,
            "uncertain_mod_files": uncertain_mod_files,
        }

    def _classify_installed_mod(
        self,
        target: Path,
        entry_path: str,
        overrides: Dict[str, str],
        files_installed: List[str],
        files_skipped: List[str],
        uncertain_mod_files: List[Dict[str, str]],
        index_env_decision: str = "",
        loader: Optional[str] = None,
    ) -> Optional[str]:
        """After downloading a mod JAR, classify and possibly remove it.

        Returns a disposition string if the file was handled, or None to let
        the caller append it to files_installed.
        """
        forced_side = overrides.get(entry_path)

        if forced_side == "client":
            target.unlink(missing_ok=True)
            files_skipped.append(entry_path)
            return "skipped"

        if forced_side == "server":
            files_installed.append(entry_path)
            return "installed"

        classification, class_reason = self._classify_mod_jar_for_server(target, loader=loader)

        if classification == "client":
            target.unlink(missing_ok=True)
            files_skipped.append(entry_path)
            return "skipped"

        if classification == "uncertain":
            if index_env_decision == "server":
                files_installed.append(entry_path)
                return "installed"
            uncertain_mod_files.append({
                "path": entry_path,
                "reason": class_reason or "Unable to detect dedicated-server compatibility from mod metadata",
            })
            return "uncertain"

        return None

    def _extract_overrides(
        self,
        zf: zipfile.ZipFile,
        install_path: Path,
        overrides: Dict[str, str],
        files_installed: List[str],
        files_skipped: List[str],
        uncertain_mod_files: List[Dict[str, str]],
        loader: Optional[str] = None,
    ) -> None:
        """Extract server-overrides/ and overrides/ from the .mrpack."""
        for member in zf.infolist():
            if member.is_dir():
                continue

            relative: Optional[str] = None
            matched_prefix = ""
            for prefix in ("server-overrides/", "overrides/"):
                if member.filename.startswith(prefix):
                    relative = member.filename[len(prefix):]
                    matched_prefix = prefix
                    break
            if not relative:
                continue

            if any(relative.lower().startswith(p) for p in self.CLIENT_ONLY_PREFIXES):
                files_skipped.append(f"{matched_prefix}{relative}")
                continue

            rel_lower = relative.lower()
            is_override_jar = rel_lower.startswith("mods/") and rel_lower.endswith(".jar")
            scoped_path = f"{matched_prefix}{relative}"

            if is_override_jar:
                forced = overrides.get(scoped_path, overrides.get(relative, ""))
                if forced == "client":
                    existing = (install_path / relative).resolve()
                    if existing.is_file() and is_within(install_path, existing):
                        existing.unlink(missing_ok=True)
                    files_skipped.append(scoped_path)
                    continue

            target = (install_path / relative).resolve()
            if not is_within(install_path, target):
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(member) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)

            if is_override_jar:
                override_lookup = {
                    scoped_path: overrides.get(scoped_path, overrides.get(relative, "")),
                }
                disposition = self._classify_installed_mod(
                    target, scoped_path,
                    override_lookup,
                    files_installed, files_skipped, uncertain_mod_files,
                    loader=loader,
                )
                if disposition is None:
                    files_installed.append(scoped_path)
            else:
                files_installed.append(scoped_path)

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
            if any(path.lower().startswith(p) for p in self.CLIENT_ONLY_PREFIXES):
                continue
            if path.lower().startswith("mods/") and path.lower().endswith(".jar"):
                decision, _reason = self._resolve_index_mod_side(path, env, overrides)
                if decision == "client":
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
            response = self.session.head(url, timeout=20, allow_redirects=True)
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
        """Resolve a single mod entry's install side from modpack index env.

        Precondition (enforced by both callers — ``_install_index_files``
        and ``_collect_unavailable_modpack_entries``): entries with
        ``env.server == "unsupported"`` are filtered out before reaching
        this helper, so that case is intentionally not handled here.
        """
        forced_side = mod_side_overrides.get(entry_path)
        if forced_side in ("client", "server"):
            return forced_side, "User override"

        server_env = str(env.get("server") or "").strip().lower()
        client_env = str(env.get("client") or "").strip().lower()

        if server_env in ("required", "optional"):
            return "server", "Index env allows server"

        if client_env == "required" and not server_env:
            return "client", "Index env requires client only (no server env specified)"

        return "uncertain", "No server env metadata in modpack index"

    def _classify_mod_jar_for_server(
        self,
        jar_path: Path,
        loader: Optional[str] = None,
    ) -> Tuple[str, str]:
        """Classify a mod JAR as client/server/uncertain for server install.

        ``loader`` selects the metadata reader to prefer when a jar ships
        multiple manifest formats (cross-compat case):

        * ``fabric``   -> ``fabric.mod.json`` only
        * ``quilt``    -> ``quilt.mod.json`` first, then ``fabric.mod.json``
        * ``forge``    -> ``META-INF/mods.toml`` only
        * ``neoforge`` -> ``META-INF/neoforge.mods.toml`` first, then
          ``META-INF/mods.toml``

        Unknown / missing loader falls back to the legacy fabric reader so
        existing call sites keep working.
        """
        loader_key = (loader or "").strip().lower()

        try:
            with zipfile.ZipFile(jar_path) as zf:
                names = set(zf.namelist())

                if loader_key == "quilt":
                    if "quilt.mod.json" in names:
                        return self._classify_quilt(zf.read("quilt.mod.json"))
                    if "fabric.mod.json" in names:
                        return self._classify_fabric(zf.read("fabric.mod.json"))
                    return "uncertain", "quilt.mod.json/fabric.mod.json missing"

                if loader_key == "forge":
                    return self._classify_forge_family(
                        zf, names, ("META-INF/mods.toml",)
                    )

                if loader_key == "neoforge":
                    return self._classify_forge_family(
                        zf, names, ("META-INF/neoforge.mods.toml", "META-INF/mods.toml")
                    )

                # fabric or unknown -> fabric.mod.json
                if "fabric.mod.json" in names:
                    return self._classify_fabric(zf.read("fabric.mod.json"))
                return "uncertain", "fabric.mod.json missing"
        except (OSError, zipfile.BadZipFile):
            return "uncertain", "Failed to parse mod metadata"

    def _classify_forge_family(
        self,
        zf: zipfile.ZipFile,
        names: set,
        toml_candidates: Tuple[str, ...],
    ) -> Tuple[str, str]:
        """Classify a Forge/NeoForge jar.

        ``toml_candidates`` is an ordered tuple of META-INF/*.toml filenames;
        the first one present in ``names`` is parsed. Falls back to the
        constant-pool scanner if metadata is uncertain. The ordering encodes
        the loader's own precedence (NeoForge prefers ``neoforge.mods.toml``;
        Forge only knows ``mods.toml``).
        """
        for candidate in toml_candidates:
            if candidate in names:
                result = self._classify_forge_toml(zf.read(candidate))
                break
        else:
            result = ("uncertain", f"{' or '.join(toml_candidates)} missing")

        if result[0] == "uncertain":
            scan_result = self._scan_class_files_for_client_imports(zf)
            if scan_result[0] == "uncertain":
                def _decap(s: str) -> str:
                    return s[0].lower() + s[1:] if s else s
                return scan_result[0], f"{result[1]}; {_decap(scan_result[1])}"
            return scan_result
        return result

    def _classify_fabric(self, raw: bytes) -> Tuple[str, str]:
        try:
            mod_meta = json.loads(raw)
        except json.JSONDecodeError:
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

    def _classify_quilt(self, raw: bytes) -> Tuple[str, str]:
        try:
            mod_meta = json.loads(raw)
        except json.JSONDecodeError:
            return "uncertain", "Failed to parse mod metadata"

        loader_block = mod_meta.get("quilt_loader") or {}
        minecraft = loader_block.get("minecraft") or {}
        environment = str(minecraft.get("environment") or "").strip().lower()

        if environment == "client":
            return "client", "quilt environment=client"
        if environment == "dedicated_server":
            return "server", "quilt environment=dedicated_server"

        return "uncertain", "quilt manifest does not clearly mark client/server"

    def _scan_class_files_for_client_imports(
        self, zf: zipfile.ZipFile,
    ) -> Tuple[str, str]:
        """Scan every .class member of ``zf`` for client-only package refs.

        Class references live in the constant pool as contiguous UTF-8
        strings (internal binary names like ``org/lwjgl/glfw/GLFW``), so
        a raw bytestring search over the file body is sufficient — no
        class-file parsing required. First hit wins; we stop scanning
        the moment any pattern matches.
        """
        for name in zf.namelist():
            if not name.endswith(".class"):
                continue
            try:
                with zf.open(name) as fh:
                    data = fh.read()
            except (KeyError, zipfile.BadZipFile, OSError):
                continue
            for pattern in self.CLIENT_ONLY_CLASS_PATTERNS:
                if pattern in data:
                    return (
                        "client",
                        f"Class file references client-only package "
                        f"{pattern.decode('ascii')}",
                    )
        return "uncertain", "No client-only class references found"

    def _classify_forge_toml(self, raw: bytes) -> Tuple[str, str]:
        """Read mods.toml / neoforge.mods.toml.

        Honored mod-side signals:

        * Top-level ``clientSideOnly = true`` (legacy Forge convention,
          e.g. EntityCulling).
        * ``[[mods]]`` table's optional ``side`` field
          (``CLIENT`` / ``SERVER`` / ``BOTH``).

        ``[[dependencies.<modid>]]`` ``side`` is intentionally NOT
        consulted: it describes the dep's side-context, not the host
        mod's. (Real example: ``configured`` declares its ``catalogue``
        dep as ``side="CLIENT"`` while ``configured`` itself is
        server-compatible.)
        """
        try:
            data = tomllib.loads(raw.decode("utf-8", errors="replace"))
        except (tomllib.TOMLDecodeError, UnicodeDecodeError):
            return "uncertain", "Failed to parse mods.toml"

        if data.get("clientSideOnly") is True:
            return "client", "mods.toml clientSideOnly=true"

        mods_list = data.get("mods")
        # Forge convention: a jar's identity is its first [[mods]] entry; subsequent
        # entries are sub-mods that share its side.
        if isinstance(mods_list, list) and mods_list:
            first = mods_list[0]
            if isinstance(first, dict):
                side = str(first.get("side") or "").strip().upper()
                if side == "CLIENT":
                    return "client", "mods.toml [[mods]] side=CLIENT"
                if side == "SERVER":
                    return "server", "mods.toml [[mods]] side=SERVER"
                if side == "BOTH":
                    return "server", "mods.toml [[mods]] side=BOTH"

        return "uncertain", "mods.toml does not declare a mod-level side"

    def clean_modpack_switch_paths(self, install_path: Path) -> List[str]:
        """Remove known modpack-managed directories before a clean switch."""
        install_root = Path(install_path).resolve()
        removed: List[str] = []

        for relative in self.MODPACK_SWITCH_PATHS:
            # Defense-in-depth: callers today iterate MODPACK_SWITCH_PATHS
            # directly (disjoint from PROTECTED_SERVER_PATHS, pinned by
            # tests/test_modrinth_client.py), so this branch is currently
            # unreachable. The guard exists so a future change adding an
            # overlapping entry to MODPACK_SWITCH_PATHS — or a future
            # caller passing a wider path-set — cannot silently delete
            # world/, logs/, backups/, libraries/, or versions/.
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
        return self._json(response, "Failed to fetch categories")

    def get_loaders(self) -> List[Dict[str, Any]]:
        response = self._request(
            "get",
            f"{self.BASE_URL}/tag/loader",
            timeout=15,
            error_context="Failed to fetch loaders",
        )
        return self._json(response, "Failed to fetch loaders")

    def get_game_versions(self) -> List[Dict[str, Any]]:
        response = self._request(
            "get",
            f"{self.BASE_URL}/tag/game_version",
            timeout=15,
            error_context="Failed to fetch game versions",
        )
        return self._json(response, "Failed to fetch game versions")
