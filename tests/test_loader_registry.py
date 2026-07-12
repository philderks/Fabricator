"""LOADER_REGISTRY and get_installer_for dispatch."""
from __future__ import annotations

from pathlib import Path

from backend.server.installer import (
    LOADER_REGISTRY,
    FabricInstaller,
    FoliaInstaller,
    ForgeInstaller,
    NeoForgeInstaller,
    PaperInstaller,
    PufferfishInstaller,
    PurpurInstaller,
    QuiltInstaller,
    VanillaInstaller,
    get_installer_for,
)


def test_registry_contains_fabric():
    assert "fabric" in LOADER_REGISTRY
    assert LOADER_REGISTRY["fabric"] is FabricInstaller


def test_get_installer_for_known_loader(tmp_path):
    inst = get_installer_for("fabric", tmp_path)
    assert isinstance(inst, FabricInstaller)


def test_get_installer_for_is_case_insensitive(tmp_path):
    inst = get_installer_for("Fabric", tmp_path)
    assert isinstance(inst, FabricInstaller)


def test_get_installer_for_unknown_returns_none(tmp_path):
    assert get_installer_for("does-not-exist", tmp_path) is None


def test_get_installer_for_empty_loader_returns_none(tmp_path):
    assert get_installer_for("", tmp_path) is None


def test_registry_contains_vanilla():
    assert "vanilla" in LOADER_REGISTRY
    assert LOADER_REGISTRY["vanilla"] is VanillaInstaller


def test_get_installer_for_vanilla(tmp_path):
    inst = get_installer_for("vanilla", tmp_path)
    assert isinstance(inst, VanillaInstaller)


def test_registry_contains_neoforge():
    assert "neoforge" in LOADER_REGISTRY
    assert LOADER_REGISTRY["neoforge"] is NeoForgeInstaller


def test_get_installer_for_neoforge(tmp_path):
    inst = get_installer_for("neoforge", tmp_path)
    assert isinstance(inst, NeoForgeInstaller)


def test_registry_contains_quilt():
    assert "quilt" in LOADER_REGISTRY
    assert LOADER_REGISTRY["quilt"] is QuiltInstaller


def test_get_installer_for_quilt(tmp_path):
    inst = get_installer_for("quilt", tmp_path)
    assert isinstance(inst, QuiltInstaller)


def test_registry_contains_forge():
    assert "forge" in LOADER_REGISTRY
    assert LOADER_REGISTRY["forge"] is ForgeInstaller


def test_get_installer_for_forge(tmp_path):
    inst = get_installer_for("forge", tmp_path)
    assert isinstance(inst, ForgeInstaller)


def test_registry_contains_bukkit_family(tmp_path):
    for name, cls in (
        ("paper", PaperInstaller),
        ("folia", FoliaInstaller),
        ("purpur", PurpurInstaller),
        ("pufferfish", PufferfishInstaller),
    ):
        assert name in LOADER_REGISTRY
        assert LOADER_REGISTRY[name] is cls
        assert isinstance(get_installer_for(name, tmp_path), cls)


def test_bukkit_family_are_plugin_kind(tmp_path):
    for name in ("paper", "folia", "purpur", "pufferfish"):
        assert get_installer_for(name, tmp_path).content_kind == "plugin"
