"""Reading and installing modpack *server packs* (#104).

Packs that only live on CurseForge (All the Mods, most kitchen-sink packs)
can't come through Modrinth, but nearly all of them publish a "Server Files"
zip per release: the pack's ``mods/``, ``config/``, ``kubejs/``... plus start
scripts and a loader installer. Uploading that zip is how a server is moved to
another pack version, forward or back.

Only the pack's top-level *folders* are installed. Top-level files are start
scripts, installer jars, ``server.properties``, ``eula.txt`` and the like —
Fabricator manages launch, loader and settings itself, so those stay as the
server has them. The loader build the pack wants is read off those same files
so the existing loader-change offer can follow the install.

Staging reuses :mod:`backend.modrinth.mrpack`; a staged server pack is told
apart by ``summary['kind'] == 'serverpack'``.
"""
from __future__ import annotations

import posixpath
import re
import shutil
import zipfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from backend.modrinth import mrpack
from backend.server.installer.neoforge import NeoForgeInstaller
from backend.utils.zip import is_within

KIND = "serverpack"

# World and server-state folders a pack must never overwrite, on top of the
# client's PROTECTED_SERVER_PATHS (world, logs, backups, libraries, versions).
_SKIPPED_DIRS = {"crash-reports", ".fabric", "world_nether", "world_the_end"}

# Start scripts and variable files are small; anything bigger is not one.
_MAX_SCRIPT_BYTES = 256 * 1024
_SCRIPT_SUFFIXES = (".sh", ".bat", ".cmd", ".ps1", ".txt", ".properties", ".cfg")

_NEOFORGE_INSTALLER = re.compile(r"^neoforge-(?P<v>\d[\w.+-]*?)-installer\.jar$", re.I)
_FORGE_INSTALLER = re.compile(r"^forge-(?P<mc>\d[\d.]*)-(?P<v>\d[\w.]*?)-installer\.jar$", re.I)
_FABRIC_LAUNCHER = re.compile(r"^fabric-server-mc\.(?P<mc>[\w.-]+?)-loader\.(?P<v>[\w.+-]+?)-launcher\.[\w.]+\.jar$", re.I)
_NEOFORGE_LIB = re.compile(r"^libraries/net/neoforged/neoforge/(?P<v>[^/]+)/")
_FORGE_LIB = re.compile(r"^libraries/net/minecraftforge/forge/(?P<mc>\d[\d.]*)-(?P<v>[^/]+)/")


def _var(text: str, *names: str) -> str:
    """Value of the first ``NAME=value`` assignment (sh, bat ``set``, ps1 ``$``)."""
    for name in names:
        match = re.search(
            rf"^\s*(?:set\s+|export\s+|\$)?{name}\s*=\s*[\"']?(?P<v>[\w.+-]+)",
            text, re.I | re.M,
        )
        if match:
            return match.group("v")
    return ""


def is_client_export(names: List[str]) -> bool:
    """A CurseForge *client* export: a manifest of project ids, not the mods."""
    return "manifest.json" in names and any(n.startswith("overrides/") for n in names)


def pack_root(names: List[str]) -> Optional[str]:
    """The prefix the pack lives under: ``""`` or one wrapping folder.

    A server pack is recognised by having a ``mods/`` folder at its root.
    """
    if any(n.startswith("mods/") for n in names):
        return ""
    tops = {n.split("/", 1)[0] for n in names if "/" in n}
    if len(tops) == 1:
        prefix = f"{tops.pop()}/"
        if any(n.startswith(f"{prefix}mods/") for n in names):
            return prefix
    return None


def _detect_loader(zf: zipfile.ZipFile, root: str) -> Dict[str, str]:
    """``{loader, loader_version, minecraft_version}``; unknowns are ``""``."""
    rel_names = [n[len(root):] for n in zf.namelist() if n.startswith(root)]
    top_files = [n for n in rel_names if n and "/" not in n]

    def found(loader: str, version: str, mc: str = "") -> Dict[str, str]:
        if loader == "neoforge" and not mc:
            mc = NeoForgeInstaller._neoforge_to_mc_version(version) or ""
        return {"loader": loader, "loader_version": version, "minecraft_version": mc}

    for name in top_files:
        if m := _NEOFORGE_INSTALLER.match(name):
            return found("neoforge", m.group("v"))
        if m := _FORGE_INSTALLER.match(name):
            return found("forge", m.group("v"), m.group("mc"))
        if m := _FABRIC_LAUNCHER.match(name):
            return found("fabric", m.group("v"), m.group("mc"))
    for name in rel_names:
        if m := _NEOFORGE_LIB.match(name):
            return found("neoforge", m.group("v"))
        if m := _FORGE_LIB.match(name):
            return found("forge", m.group("v"), m.group("mc"))

    # No installer shipped: the start script downloads it, so the build is a
    # variable in there (ATM's NEOFORGE_VERSION, ServerPackCreator's
    # variables.txt MODLOADER/MODLOADER_VERSION).
    for name in top_files:
        info = zf.getinfo(root + name)
        if not name.lower().endswith(_SCRIPT_SUFFIXES) or info.file_size > _MAX_SCRIPT_BYTES:
            continue
        text = zf.read(info).decode("utf-8", errors="replace")
        mc = _var(text, "MINECRAFT_VERSION", "MC_VERSION")
        if v := _var(text, "NEOFORGE_VERSION"):
            return found("neoforge", v, mc)
        if v := _var(text, "FORGE_VERSION"):
            # Some scripts write the full ``<mc>-<build>`` coordinate.
            head, sep, tail = v.partition("-")
            return found("forge", tail, head) if sep and "." in head else found("forge", v, mc)
        if v := _var(text, "FABRIC_LOADER_VERSION", "FABRIC_VERSION"):
            return found("fabric", v, mc)
        loader = _var(text, "MODLOADER").lower()
        if loader in {"neoforge", "forge", "fabric", "quilt"}:
            return found(loader, _var(text, "MODLOADER_VERSION"), mc)
    return {"loader": "", "loader_version": "", "minecraft_version": ""}


def describe(archive_path: Path, filename: str) -> Dict[str, Any]:
    """Validate a server pack and summarize it in the shape of ``mrpack.describe``.

    Raises :class:`mrpack.InvalidMrpackError` with a message for the user.
    """
    try:
        with zipfile.ZipFile(archive_path) as zf:
            mrpack._check_extracted_size(zf)
            names = zf.namelist()
            if is_client_export(names):
                raise mrpack.InvalidMrpackError(
                    "This is a CurseForge client export, which lists mods instead of "
                    "including them. Download the pack's Server Files zip instead."
                )
            root = pack_root(names)
            if root is None:
                raise mrpack.InvalidMrpackError(
                    "Archive is neither a Modrinth modpack (.mrpack) nor a server pack "
                    "(a zip with a mods/ folder)"
                )
            detected = _detect_loader(zf, root)
    except zipfile.BadZipFile:
        raise mrpack.InvalidMrpackError("Upload is not a readable zip archive") from None
    except OSError as exc:
        raise mrpack.InvalidMrpackError(f"Could not read the uploaded file: {exc}") from exc

    stem = Path(filename).stem
    versions = re.findall(r"\d+(?:\.\d+)+", stem)
    dependencies = {"minecraft": detected["minecraft_version"]} if detected["minecraft_version"] else {}
    dependency_key = {v: k for k, v in mrpack.LOADER_DEPENDENCY_KEYS.items()}.get(detected["loader"])
    if dependency_key and detected["loader_version"]:
        dependencies[dependency_key] = detected["loader_version"]
    return {
        "kind": KIND,
        "root": root,
        "name": stem,
        # shortcut: the pack version is guessed from the file name (last dotted
        # number); good enough for display, nothing compares it.
        "version": versions[-1] if versions else "",
        "summary": "",
        **detected,
        "file_count": sum(
            1 for n in names if n.startswith(f"{root}mods/") and n.lower().endswith(".jar")
        ),
        "client_only_count": 0,
        "dependencies": dependencies,
    }


def install(
    archive_path: Path,
    install_path: Path,
    summary: Dict[str, Any],
    *,
    clean: Callable[[Path], List[str]],
    protected: set,
    clean_install: bool = True,
    progress_callback: Optional[Callable[..., None]] = None,
) -> Dict[str, Any]:
    """Replace the server's pack content with the pack's top-level folders.

    ``clean`` removes the pack-managed folders (the client's modpack-switch
    list) and runs only once the archive has been opened, so an unreadable
    upload leaves the server untouched.
    """
    def _report(stage: str, current: int = 0, total: int = 0, detail: str = "") -> None:
        if progress_callback:
            progress_callback(stage=stage, current=current, total=total, detail=detail)

    install_path = Path(install_path).resolve()
    root = summary.get("root") or ""
    skipped_dirs = set(protected) | _SKIPPED_DIRS
    installed: List[str] = []
    skipped: List[str] = []
    cleaned: List[str] = []

    with zipfile.ZipFile(archive_path) as zf:
        members = [m for m in zf.infolist() if m.filename.startswith(root) and not m.is_dir()]
        # A pack that ships a default world must not land on the server's own,
        # whatever its level-name.
        skipped_dirs |= {
            m.filename[len(root):].split("/", 1)[0]
            for m in members if m.filename.endswith("/level.dat")
        }
        if clean_install:
            _report("cleaning")
            cleaned = clean(install_path)
        _report("extracting_overrides", 0, len(members))
        for index, member in enumerate(members, 1):
            relative = posixpath.normpath(member.filename[len(root):])
            top = relative.split("/", 1)[0]
            if "/" not in relative or top in skipped_dirs:
                skipped.append(relative)
                continue
            target = (install_path / relative).resolve()
            if not is_within(install_path, target):
                skipped.append(relative)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(member) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)
            installed.append(relative)
            if index % 200 == 0:
                _report("extracting_overrides", index, len(members))

    return {
        "version": summary.get("version"),
        "name": summary.get("name"),
        "version_name": summary.get("version"),
        "mc_version": summary.get("minecraft_version") or None,
        "loaders": [summary["loader"]] if summary.get("loader") else [],
        "project_id": None,
        "version_id": None,
        "files_installed": installed,
        "files_skipped": skipped,
        "clean_install": clean_install,
        "cleaned_paths": cleaned,
        "missing_files": [],
        "allow_missing": False,
        "dependencies": summary.get("dependencies") or {},
        "uncertain_mod_files": [],
    }
