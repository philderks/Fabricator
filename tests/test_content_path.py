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
    reg = _make_registry(tmp_path)
    path = reg.resolve_content_path(_server("mystery"))
    assert path.name == "mods"


def test_resolve_mods_path_alias_tracks_content_path(tmp_path):
    reg = _make_registry(tmp_path)
    assert reg.resolve_mods_path(_server("paper")).name == "plugins"
    assert reg.resolve_mods_path(_server("fabric")).name == "mods"
