"""LOADER_REGISTRY and get_installer_for dispatch."""
from __future__ import annotations

from pathlib import Path

from backend.server.installer import (
    LOADER_REGISTRY,
    FabricInstaller,
    NeoForgeInstaller,
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
