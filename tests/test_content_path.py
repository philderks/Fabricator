"""ServerProcessRegistry.resolve_content_path — mods/ vs plugins/ by loader."""
from __future__ import annotations


def _make_registry(tmp_path):
    from backend.server.registry import ServerProcessRegistry
    return ServerProcessRegistry(tmp_path)


def _server(loader):
    return {"id": "srv_x", "loader": loader, "installPath": "srv_x"}


def test_mod_loader_uses_mods_folder(tmp_path):
    reg = _make_registry(tmp_path)
    path = reg.resolve_content_path(_server("fabric"))
    assert path.name == "mods"
    assert path.is_dir()


def test_plugin_loaders_use_plugins_folder(tmp_path):
    reg = _make_registry(tmp_path)
    for loader in ("paper", "purpur", "folia", "pufferfish"):
        path = reg.resolve_content_path(_server(loader))
        assert path.name == "plugins", loader
        assert path.is_dir()


def test_unknown_loader_defaults_to_mods(tmp_path):
    # Fail open: a loader not in the registry still gets a mods/ surface rather
    # than being treated as content-less.
    reg = _make_registry(tmp_path)
    path = reg.resolve_content_path(_server("mystery"))
    assert path.name == "mods"


def test_loader_content_kind_lookup_is_allocation_free():
    """loader_content_kind must read the class attr, not build an installer.

    Constructing a plugin installer opens a requests.Session; this lookup runs
    on the polled server-list path, so it must not construct one.
    """
    from unittest.mock import patch
    from backend.server import installer as installer_pkg

    with patch.object(installer_pkg, "get_installer_for") as spy:
        assert installer_pkg.loader_content_kind("paper") == "plugin"
        assert installer_pkg.loader_content_kind("fabric") == "mod"
        assert installer_pkg.loader_content_kind("mystery") == "mod"  # fail open
        assert installer_pkg.loader_content_kind("vanilla") is None
        spy.assert_not_called()


def test_resolve_mods_path_alias_tracks_content_path(tmp_path):
    reg = _make_registry(tmp_path)
    assert reg.resolve_mods_path(_server("paper")).name == "plugins"
    assert reg.resolve_mods_path(_server("fabric")).name == "mods"
