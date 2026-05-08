"""Server installer package."""
from pathlib import Path
from typing import Dict, Optional, Type

from .base import (  # noqa: F401
    InstallerBase,
    InstallResult,
    InstallStatus,
    LaunchSpec,
)
from .fabric import FabricInstaller  # noqa: F401
from .vanilla import VanillaInstaller  # noqa: F401
from .neoforge import NeoForgeInstaller  # noqa: F401


LOADER_REGISTRY: Dict[str, Type[InstallerBase]] = {
    "fabric": FabricInstaller,
    "vanilla": VanillaInstaller,
    "neoforge": NeoForgeInstaller,
}


def get_installer_for(loader: str, install_path: Path) -> Optional[InstallerBase]:
    """Return a configured installer for ``loader`` or ``None`` if unknown.

    Lookup is case-insensitive. Empty/whitespace loader strings return None.
    """
    if not loader or not loader.strip():
        return None
    cls = LOADER_REGISTRY.get(loader.strip().lower())
    if cls is None:
        return None
    return cls(install_path)


def supported_loaders() -> list[str]:
    """Return the list of registered loader names (lowercase)."""
    return sorted(LOADER_REGISTRY.keys())
