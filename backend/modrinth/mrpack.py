"""Reading and staging user-supplied Modrinth modpack archives (.mrpack).

A .mrpack is a zip holding ``modrinth.index.json`` — the pack manifest —
alongside optional ``overrides/`` and ``server-overrides/`` trees. The index
lists every mod as a download URL plus hashes instead of embedding the jar,
so an archive stays small even when it installs a gigabyte of mods.

Fabricator already installs packs it fetches from Modrinth itself
(:meth:`ModrinthClient.install_modpack`). This module covers the other
direction (#53): a pack the user exported from the Modrinth app, which has
no project id and no upstream version to resolve — so its Minecraft version
and loader have to be read out of the index's ``dependencies`` block.

Uploads are **staged** rather than installed on arrival, because during
server creation the server does not exist yet when the file is uploaded:
the create form reads the loader and Minecraft version off the parsed index
to fill itself in, and the install happens later, once the loader is on
disk. Staging also means the retry paths (missing files, uncertain mod
sides) can re-run an install without asking for the file a second time.
"""
from __future__ import annotations

import json
import logging
import threading
import time
import uuid
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.core.config import get_config
from backend.utils.upload import env_max_bytes

logger = logging.getLogger(__name__)

INDEX_NAME = "modrinth.index.json"

# Upload cap. A pack is mostly a manifest, but `overrides/` carries configs
# and the odd bundled jar, so a few hundred MB is realistic; 2 GiB leaves
# room without letting a stray file fill the disk.
_DEFAULT_MAX_UPLOAD_BYTES = 2 * 1024 * 1024 * 1024

# Zip-bomb ceiling: the sum of every member's *uncompressed* size, read from
# the central directory before anything is extracted. Overrides trees are
# large but not this large.
_DEFAULT_MAX_EXTRACTED_BYTES = 16 * 1024 * 1024 * 1024

# The index itself is JSON we parse into memory, so it gets a much tighter
# cap than the archive as a whole.
_MAX_INDEX_BYTES = 32 * 1024 * 1024

# Staged uploads expire so an abandoned create dialog doesn't leave archives
# behind forever.
STAGING_TTL_SECONDS = 6 * 60 * 60

# Maps a `dependencies` key to the loader name Fabricator installs under.
# Ordered: a Quilt pack may list `fabric-loader` too (Quilt runs Fabric
# mods), and there the Quilt entry is the one that describes the pack.
LOADER_DEPENDENCY_KEYS = {
    "quilt-loader": "quilt",
    "fabric-loader": "fabric",
    "neoforge": "neoforge",
    "forge": "forge",
}


class InvalidMrpackError(Exception):
    """Raised when an upload is not a readable Modrinth modpack archive."""


def max_upload_bytes() -> int:
    """Return the configured .mrpack upload cap in bytes."""
    return env_max_bytes(
        "FABRICATOR_MAX_MRPACK_UPLOAD_BYTES", _DEFAULT_MAX_UPLOAD_BYTES
    )


def max_extracted_bytes() -> int:
    """Return the configured cap on a pack's total uncompressed size."""
    return env_max_bytes(
        "FABRICATOR_MAX_MRPACK_EXTRACTED_BYTES", _DEFAULT_MAX_EXTRACTED_BYTES
    )


def staging_dir() -> Path:
    """Directory holding uploaded-but-not-yet-installed archives.

    Shares the ``.uploads`` folder the world importer already uses, so both
    kinds of upload land in one place an operator can inspect or clear.
    """
    return Path(get_config().SERVERS_ROOT) / ".uploads"


# ---------------------------------------------------------------------------
# Index parsing
# ---------------------------------------------------------------------------


def read_index(archive_path: Path) -> Dict[str, Any]:
    """Read and validate ``modrinth.index.json`` out of ``archive_path``.

    Only the manifest is parsed — no member is extracted — so this is cheap
    enough to run inline on the upload request. Raises
    :class:`InvalidMrpackError` with a message meant for the user.
    """
    try:
        with zipfile.ZipFile(archive_path) as zf:
            try:
                info = zf.getinfo(INDEX_NAME)
            except KeyError:
                raise InvalidMrpackError(
                    "Archive does not contain modrinth.index.json — it is not "
                    "a Modrinth modpack (.mrpack) file"
                ) from None

            _check_extracted_size(zf)

            if info.file_size > _MAX_INDEX_BYTES:
                raise InvalidMrpackError("modrinth.index.json is implausibly large")

            with zf.open(info) as fh:
                raw = fh.read(_MAX_INDEX_BYTES + 1)
    except zipfile.BadZipFile:
        raise InvalidMrpackError(
            "Upload is not a readable .mrpack file (a .mrpack is a zip archive)"
        ) from None
    except OSError as exc:
        raise InvalidMrpackError(f"Could not read the uploaded file: {exc}") from exc

    try:
        index = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise InvalidMrpackError("modrinth.index.json is not valid JSON") from None

    if not isinstance(index, dict):
        raise InvalidMrpackError("modrinth.index.json is not a JSON object")

    game = str(index.get("game") or "minecraft").strip().lower()
    if game != "minecraft":
        raise InvalidMrpackError(f"This modpack targets '{game}', not Minecraft")

    files = index.get("files")
    if files is not None and not isinstance(files, list):
        raise InvalidMrpackError("modrinth.index.json has a malformed 'files' list")

    dependencies = index.get("dependencies")
    if dependencies is not None and not isinstance(dependencies, dict):
        raise InvalidMrpackError(
            "modrinth.index.json has a malformed 'dependencies' block"
        )

    return index


def _check_extracted_size(zf: zipfile.ZipFile) -> None:
    """Reject an archive whose members expand past the configured ceiling."""
    limit = max_extracted_bytes()
    total = 0
    for member in zf.infolist():
        total += member.file_size
        if total > limit:
            raise InvalidMrpackError(
                f"Archive expands to more than the {limit}-byte limit"
            )


def describe(index: Dict[str, Any], archive_path: Optional[Path] = None) -> Dict[str, Any]:
    """Summarize a parsed index for the UI.

    ``loader`` / ``minecraft_version`` are what the create form fills itself
    in from, so they are normalized here rather than in the route. Anything
    the pack does not declare comes back as an empty string — the caller
    decides whether that is fatal.
    """
    dependencies = index.get("dependencies") or {}

    loader = ""
    loader_version = ""
    for key, name in LOADER_DEPENDENCY_KEYS.items():
        declared = dependencies.get(key)
        if declared:
            loader = name
            loader_version = str(declared).strip()
            break

    files = index.get("files") or []
    client_only = 0
    for entry in files:
        if not isinstance(entry, dict):
            continue
        env = entry.get("env") or {}
        if isinstance(env, dict) and str(env.get("server") or "").lower() == "unsupported":
            client_only += 1

    summary = {
        "name": str(index.get("name") or "").strip(),
        "version": str(index.get("versionId") or "").strip(),
        "summary": str(index.get("summary") or "").strip(),
        "minecraft_version": str(dependencies.get("minecraft") or "").strip(),
        "loader": loader,
        "loader_version": loader_version,
        "file_count": len(files),
        "client_only_count": client_only,
        "dependencies": {str(k): str(v) for k, v in dependencies.items()},
    }

    if archive_path is not None:
        summary.update(_override_flags(archive_path))

    return summary


def _override_flags(archive_path: Path) -> Dict[str, bool]:
    """Report which override trees a pack carries (listing only, no reads)."""
    has_overrides = False
    has_server_overrides = False
    try:
        with zipfile.ZipFile(archive_path) as zf:
            for name in zf.namelist():
                if name.startswith("server-overrides/"):
                    has_server_overrides = True
                elif name.startswith("overrides/"):
                    has_overrides = True
                if has_overrides and has_server_overrides:
                    break
    except (zipfile.BadZipFile, OSError):  # pragma: no cover - already validated
        pass
    return {
        "has_overrides": has_overrides,
        "has_server_overrides": has_server_overrides,
    }


def compare_with_server(summary: Dict[str, Any], server: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Report how ``summary`` disagrees with the server it targets, or None.

    A pack declares the Minecraft version and loader it was built against.
    Installing it onto a server running something else usually produces a
    server that will not boot, so the mismatch is surfaced for the user to
    confirm — not silently corrected, since only they know whether the pack
    happens to be portable.
    """
    pack_mc = str(summary.get("minecraft_version") or "").strip()
    pack_loader = str(summary.get("loader") or "").strip().lower()
    server_mc = str(server.get("version") or "").strip()
    server_loader = str(server.get("loader") or "").strip().lower()

    reasons: List[str] = []
    if pack_mc and server_mc and pack_mc != server_mc:
        reasons.append(
            f"the pack targets Minecraft {pack_mc} but this server runs {server_mc}"
        )
    if pack_loader and server_loader and pack_loader != server_loader:
        reasons.append(
            f"the pack targets {pack_loader} but this server uses {server_loader}"
        )

    if not reasons:
        return None

    return {
        "pack_mc_version": pack_mc,
        "pack_loader": pack_loader,
        "server_mc_version": server_mc,
        "server_loader": server_loader,
        "reasons": reasons,
    }


# ---------------------------------------------------------------------------
# Staging store
# ---------------------------------------------------------------------------


@dataclass
class StagedPack:
    """An uploaded archive waiting to be installed onto a server."""

    upload_id: str
    path: Path
    filename: str
    size_bytes: int
    summary: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)

    def to_payload(self) -> Dict[str, Any]:
        return {
            "upload_id": self.upload_id,
            "filename": self.filename,
            "size_bytes": self.size_bytes,
            **self.summary,
        }


_staged: Dict[str, StagedPack] = {}
_staged_lock = threading.Lock()


def stage(path: Path, *, filename: str, size_bytes: int, summary: Dict[str, Any]) -> StagedPack:
    """Register an already-written archive and return its handle."""
    pack = StagedPack(
        upload_id=uuid.uuid4().hex,
        path=path,
        filename=filename,
        size_bytes=size_bytes,
        summary=summary,
    )
    with _staged_lock:
        _staged[pack.upload_id] = pack
    return pack


def get(upload_id: str) -> Optional[StagedPack]:
    """Return a staged pack whose file is still on disk, or None.

    The id is looked up in the registry rather than joined onto a directory,
    so a caller cannot reach a path of their choosing through it.
    """
    with _staged_lock:
        pack = _staged.get(str(upload_id or ""))
    if pack is None:
        return None
    if not pack.path.is_file():
        discard(pack.upload_id)
        return None
    return pack


def discard(upload_id: str) -> bool:
    """Drop a staged pack and delete its file. True if one was registered."""
    with _staged_lock:
        pack = _staged.pop(str(upload_id or ""), None)
    if pack is None:
        return False
    try:
        pack.path.unlink(missing_ok=True)
    except OSError as exc:  # pragma: no cover - best effort cleanup
        logger.warning("Could not remove staged modpack %s: %s", pack.path, exc)
    return True


def sweep_expired(now: Optional[float] = None) -> int:
    """Delete staged packs past the TTL. Returns how many were removed.

    Also sweeps orphaned files in the staging directory: the registry lives
    in memory, so a restart between upload and install would otherwise leave
    an archive on disk that nothing remembers.
    """
    moment = time.time() if now is None else now
    cutoff = moment - STAGING_TTL_SECONDS

    with _staged_lock:
        expired = [p.upload_id for p in _staged.values() if p.created_at < cutoff]
        live_paths = {p.path for p in _staged.values()}

    removed = 0
    for upload_id in expired:
        if discard(upload_id):
            removed += 1

    try:
        candidates = list(staging_dir().glob("mrpack-*.mrpack"))
    except OSError:  # pragma: no cover - unreadable staging dir
        return removed

    for orphan in candidates:
        if orphan in live_paths:
            continue
        try:
            if orphan.stat().st_mtime >= cutoff:
                continue
            orphan.unlink()
            removed += 1
        except OSError:  # pragma: no cover - best effort cleanup
            continue

    return removed


def reset_for_tests() -> None:
    """Drop every staged pack (and its file). Test-support only."""
    with _staged_lock:
        ids = list(_staged)
    for upload_id in ids:
        discard(upload_id)
