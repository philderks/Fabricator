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
from .quilt import QuiltInstaller  # noqa: F401
from .forge import ForgeInstaller  # noqa: F401
from .papermc import PaperInstaller, FoliaInstaller  # noqa: F401
from .purpur import PurpurInstaller  # noqa: F401
from .pufferfish import PufferfishInstaller  # noqa: F401


LOADER_REGISTRY: Dict[str, Type[InstallerBase]] = {
    "fabric": FabricInstaller,
    "vanilla": VanillaInstaller,
    "neoforge": NeoForgeInstaller,
    "quilt": QuiltInstaller,
    "forge": ForgeInstaller,
    "paper": PaperInstaller,
    "folia": FoliaInstaller,
    "purpur": PurpurInstaller,
    "pufferfish": PufferfishInstaller,
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


def loader_content_kind(loader: str) -> Optional[str]:
    """Return a loader's add-on content kind without building an installer.

    ``content_kind`` is a class attribute on each installer, so this is a pure
    registry lookup that allocates nothing — important because installers open
    a ``requests.Session`` on construction and the mods-/plugins-folder is
    resolved on the polled server-list path (``_augment_with_runtime``).

    Returns ``"plugin"`` / ``"mod"`` / ``None``. Unknown loaders default to
    ``"mod"`` (they still have a ``mods/`` surface — fail open, mirroring the
    frontend); empty/blank input returns ``None``.
    """
    if not loader or not loader.strip():
        return None
    cls = LOADER_REGISTRY.get(loader.strip().lower())
    if cls is None:
        return "mod"
    return cls.content_kind
