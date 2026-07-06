"""Atomic, path-guarded JSON list I/O for the Minecraft server data files.

The Minecraft server writes whitelist.json / ops.json / banned-players.json
non-atomically — a read during a server-side write can land on a partial
file (JSONDecodeError). One quick retry tolerates that race; anything
persistent surfaces as a normal decode error.
"""
import hashlib
import json
import os
import tempfile
import time
import uuid
from pathlib import Path
from typing import Iterable, List, Optional, Union


JsonList = List[dict]


class NotAJsonList(ValueError):
    """Raised when the file decoded successfully but is not a JSON list."""


_RETRY_DELAY_SECONDS = 0.05


def _resolve_within(server_dir: Path, relative: str) -> Path:
    """Resolve `relative` under `server_dir` and refuse any escape."""
    candidate = (server_dir / relative).resolve()
    server_dir_resolved = server_dir.resolve()
    try:
        candidate.relative_to(server_dir_resolved)
    except ValueError as exc:
        raise ValueError(
            f"Path {relative!r} escapes server directory"
        ) from exc
    return candidate


def read_json_list(server_dir: Union[str, Path], relative: str) -> JsonList:
    """Read a JSON list file under `server_dir`.

    Missing file → []. Transient JSONDecodeError (partial write by Minecraft)
    is retried once after a short sleep.
    """
    path = _resolve_within(Path(server_dir), relative)
    if not path.exists():
        return []

    try:
        return _decode_list(path)
    except json.JSONDecodeError:
        time.sleep(_RETRY_DELAY_SECONDS)
        return _decode_list(path)


def _decode_list(path: Path) -> JsonList:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise NotAJsonList(
            f"Expected list in {path.name}, got {type(data).__name__}"
        )
    return data


def write_json_list(
    server_dir: Union[str, Path],
    relative: str,
    entries: Iterable[dict],
) -> None:
    """Atomically write a JSON list. Creates parent directories as needed."""
    path = _resolve_within(Path(server_dir), relative)
    path.parent.mkdir(parents=True, exist_ok=True)

    serialised = json.dumps(list(entries), indent=2)

    # Write to a sibling temp file then atomically replace — never leaves a
    # half-written file at the target path.
    fd, tmp_name = tempfile.mkstemp(
        prefix=path.name + ".",
        suffix=".tmp",
        dir=path.parent,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(serialised)
        Path(tmp_name).replace(path)
    except Exception:
        # Best-effort cleanup; intentionally swallow secondary errors.
        try:
            Path(tmp_name).unlink(missing_ok=True)
        except Exception:  # pragma: no cover
            pass
        raise


def offline_uuid(name: str) -> uuid.UUID:
    """Compute the UUID Minecraft uses for offline-mode players.

    Equivalent to Java's `UUID.nameUUIDFromBytes(("OfflinePlayer:" + name).getBytes(UTF_8))`:
    MD5 of the prefixed bytes, then set version=3 and the RFC 4122 variant.
    This is *not* the same as Python's `uuid.uuid3` (which XORs with a
    namespace UUID first).
    """
    digest = bytearray(hashlib.md5(("OfflinePlayer:" + name).encode("utf-8")).digest())
    digest[6] = (digest[6] & 0x0F) | 0x30
    digest[8] = (digest[8] & 0x3F) | 0x80
    return uuid.UUID(bytes=bytes(digest))


def find_entry_by_name(entries: JsonList, name: str) -> Optional[dict]:
    """Case-insensitive lookup by 'name' field. Returns the dict or None."""
    target = name.lower()
    for entry in entries:
        if str(entry.get("name", "")).lower() == target:
            return entry
    return None
