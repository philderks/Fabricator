"""Inspect a Minecraft server folder Fabricator did not create.

Read-only: works out the loader, Minecraft version and launch target from the
files a server leaves behind, so the import form can be prefilled. Anything it
cannot tell is left as ``None`` with a warning — the user confirms or corrects
the guess before anything is registered.
"""
from __future__ import annotations

import json
import os
import re
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.server.installer import loader_content_kind
from backend.server.installer.neoforge import NeoForgeInstaller
from backend.utils.platform import is_windows
from backend.utils.strings import unescape_properties_value


_PAPER_FAMILY = ('paper', 'purpur', 'folia', 'pufferfish')
_MC_VERSION = r'\d+\.\d+(?:\.\d+)?'

_FORGE_LEGACY_JAR = re.compile(
    rf'^(?:forge-(?P<mc>{_MC_VERSION})-[\w.]+?(?:-universal)?'
    rf'|minecraftforge-universal-(?P<mc2>{_MC_VERSION})-[\w.]+)\.jar$'
)
_FABRIC_LAUNCHER_JAR = re.compile(
    rf'^fabric-server-mc\.(?P<mc>[\w.-]+?)-loader\.(?P<loader>[\w.+-]+?)-launcher\.[\w.]+\.jar$'
)
_PAPER_JAR = re.compile(
    rf'^(?P<loader>{"|".join(_PAPER_FAMILY)})-(?P<mc>{_MC_VERSION})(?:-[\w.-]+)?\.jar$',
    re.IGNORECASE,
)
_PAPER_HISTORY = re.compile(rf'(?P<loader>{"|".join(_PAPER_FAMILY)})', re.IGNORECASE)
_HISTORY_MC = re.compile(rf'\(MC: (?P<mc>[^)]+)\)|^(?P<mc2>{_MC_VERSION})-')


def validate_folder(raw_path: Any) -> Path:
    """Return ``raw_path`` resolved, or raise ``ValueError`` if it is not importable.

    This is the trust boundary for an absolute path typed into the panel: an
    in-place import makes the folder browsable through the file manager, so a
    drive root or home folder is refused outright and anything else must at
    least look like a server.
    """
    text = str(raw_path or '').strip()
    if not text:
        raise ValueError('Path is required')
    path = Path(text).expanduser()
    if not path.is_absolute():
        raise ValueError('Path must be absolute')
    path = path.resolve()
    if not path.is_dir():
        raise ValueError(f"Folder '{path}' does not exist")
    if path == Path(path.anchor) or path == Path.home().resolve():
        raise ValueError('Refusing to import a drive root or home folder')
    looks_like_server = (
        (path / 'server.properties').is_file()
        or (path / 'eula.txt').is_file()
        or any(path.glob('*.jar'))
    )
    if not looks_like_server:
        raise ValueError(
            'Folder does not look like a Minecraft server '
            '(no server.properties, eula.txt or server jar)'
        )
    return path


def read_properties(path: Path) -> Dict[str, str]:
    """Parse ``server.properties`` into ``{key: value}``; ``{}`` if unreadable."""
    try:
        text = (path / 'server.properties').read_text(encoding='utf-8')
    except (OSError, UnicodeDecodeError):
        return {}
    props: Dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith(('#', '!')) or '=' not in line:
            continue
        key, value = line.split('=', 1)
        props[key.strip()] = unescape_properties_value(value)
    return props


def _jar_mc_version(jar: Path) -> Optional[str]:
    """``id`` from the ``version.json`` Mojang ships inside every server jar."""
    try:
        with zipfile.ZipFile(jar) as archive:
            data = json.loads(archive.read('version.json'))
    except (OSError, KeyError, ValueError, zipfile.BadZipFile):
        return None
    return data.get('id') or data.get('name') if isinstance(data, dict) else None


def _single_child(path: Path) -> Optional[str]:
    """Name of the only subdirectory of ``path``, else ``None``."""
    if not path.is_dir():
        return None
    children = [child.name for child in path.iterdir() if child.is_dir()]
    return children[0] if len(children) == 1 else None


def _jar_launch(jar: str) -> Dict[str, Any]:
    return {'type': 'jar', 'jar': jar, 'jvm_args': [], 'program_args': ['nogui'], 'args_file': None}


def _args_file_launch(path: Path, root: Path) -> Dict[str, Any]:
    return {
        'type': 'args_file', 'jar': None, 'jvm_args': [], 'program_args': ['nogui'],
        'args_file': path.relative_to(root).as_posix(),
    }


def _detect(path: Path, jars: List[str]) -> Dict[str, Any]:
    """Return ``{loader, version, loaderVersion, launch}``; unknowns are ``None``."""
    args_name = 'win_args.txt' if is_windows() else 'unix_args.txt'

    neo_version = _single_child(path / 'libraries' / 'net' / 'neoforged' / 'neoforge')
    if neo_version and (path / 'libraries/net/neoforged/neoforge' / neo_version / args_name).is_file():
        return {
            'loader': 'neoforge',
            'version': NeoForgeInstaller._neoforge_to_mc_version(neo_version),
            'loaderVersion': neo_version,
            'launch': _args_file_launch(
                path / 'libraries/net/neoforged/neoforge' / neo_version / args_name, path
            ),
        }

    forge_version = _single_child(path / 'libraries' / 'net' / 'minecraftforge' / 'forge')
    if forge_version and (path / 'libraries/net/minecraftforge/forge' / forge_version / args_name).is_file():
        mc, _, build = forge_version.partition('-')
        return {
            'loader': 'forge', 'version': mc, 'loaderVersion': build or None,
            'launch': _args_file_launch(
                path / 'libraries/net/minecraftforge/forge' / forge_version / args_name, path
            ),
        }

    for jar in jars:
        match = _FORGE_LEGACY_JAR.match(jar)
        if match and 'installer' not in jar:
            return {
                'loader': 'forge', 'version': match.group('mc') or match.group('mc2'),
                'loaderVersion': None, 'launch': _jar_launch(jar),
            }

    for jar in jars:
        match = _FABRIC_LAUNCHER_JAR.match(jar)
        if match:
            return {
                'loader': 'fabric', 'version': match.group('mc'),
                'loaderVersion': match.group('loader'), 'launch': _jar_launch(jar),
            }

    for loader in ('fabric', 'quilt'):
        if f'{loader}-server-launch.jar' in jars:
            return {
                'loader': loader, 'version': None, 'loaderVersion': None,
                'launch': _jar_launch(f'{loader}-server-launch.jar'),
            }

    history = path / 'version_history.json'
    if history.is_file():
        try:
            current = str(json.loads(history.read_text(encoding='utf-8')).get('currentVersion') or '')
        except (OSError, ValueError, AttributeError):
            current = ''
        loader_match = _PAPER_HISTORY.search(current)
        mc_match = _HISTORY_MC.search(current)
        if loader_match:
            loader = loader_match.group('loader').lower()
            jar = next((jar for jar in jars if jar.lower().startswith(loader)), None) or _main_jar(jars)
            return {
                'loader': loader,
                'version': (mc_match.group('mc') or mc_match.group('mc2')) if mc_match else None,
                'loaderVersion': None,
                'launch': _jar_launch(jar) if jar else None,
            }

    for jar in jars:
        match = _PAPER_JAR.match(jar)
        if match:
            return {
                'loader': match.group('loader').lower(), 'version': match.group('mc'),
                'loaderVersion': None, 'launch': _jar_launch(jar),
            }

    main = _main_jar(jars)
    if main and _jar_mc_version(path / main):
        return {'loader': 'vanilla', 'version': None, 'loaderVersion': None, 'launch': _jar_launch(main)}

    return {
        'loader': None, 'version': None, 'loaderVersion': None,
        'launch': _jar_launch(main) if main else None,
    }


def _main_jar(jars: List[str]) -> Optional[str]:
    """``server.jar`` if present, else the only jar in the folder."""
    if 'server.jar' in jars:
        return 'server.jar'
    candidates = [jar for jar in jars if 'installer' not in jar]
    return candidates[0] if len(candidates) == 1 else None


def _fallback_mc_version(path: Path, jars: List[str]) -> Optional[str]:
    """The Minecraft version when the loader layout itself did not say."""
    # Fabric/Quilt launchers and Paperclip keep the vanilla jar next to them.
    for jar in ['server.jar', *jars]:
        if jar in jars:
            version = _jar_mc_version(path / jar)
            if version:
                return version
    return (
        _single_child(path / 'libraries' / 'net' / 'minecraft' / 'server')
        or _single_child(path / 'versions')
    )


def inspect_folder(path: Path) -> Dict[str, Any]:
    """Describe the server in ``path`` (already passed through :func:`validate_folder`)."""
    jars = sorted(entry.name for entry in path.iterdir() if entry.is_file() and entry.suffix == '.jar')
    detected = _detect(path, jars)
    if not detected['version']:
        detected['version'] = _fallback_mc_version(path, jars)

    props = read_properties(path)
    try:
        port = int(props.get('server-port', ''))
    except ValueError:
        port = None

    content_dir = path / ('plugins' if loader_content_kind(detected['loader'] or '') == 'plugin' else 'mods')
    mods_count = (
        sum(1 for entry in content_dir.iterdir() if entry.name.lower().endswith('.jar'))
        if content_dir.is_dir() else 0
    )

    warnings = []
    if not detected['loader']:
        warnings.append('loader')
    if not detected['version']:
        warnings.append('version')
    if not detected['launch']:
        warnings.append('launch')
    if not os.access(path, os.R_OK | os.W_OK):
        warnings.append('permissions')

    return {
        'path': str(path),
        'name': path.name,
        'port': port,
        'modsCount': mods_count,
        # Codes, not prose — the frontend owns the wording (i18n).
        'warnings': warnings,
        **detected,
    }
