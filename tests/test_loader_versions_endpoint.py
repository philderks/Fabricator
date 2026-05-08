"""Generic versions endpoints under /api/loaders/<loader>/."""
from __future__ import annotations

from unittest.mock import patch


def test_game_versions_dispatch_to_fabric(client):
    fake_versions = [
        {"version": "1.21.4", "stable": True},
        {"version": "24w45a", "stable": False},
    ]
    with patch(
        "backend.server.installer.fabric.FabricInstaller.get_minecraft_versions",
        return_value=fake_versions,
    ):
        resp = client.get("/api/loaders/fabric/versions/game")

    assert resp.status_code == 200
    assert resp.get_json() == fake_versions


def test_loader_versions_dispatch_to_fabric(client):
    fake = [{"loader": {"version": "0.16.0", "stable": True}}]
    with patch(
        "backend.server.installer.fabric.FabricInstaller.get_available_versions",
        return_value=fake,
    ) as mock:
        resp = client.get("/api/loaders/fabric/versions/loader?mc_version=1.21.4")

    assert resp.status_code == 200
    assert resp.get_json() == fake
    mock.assert_called_once_with("1.21.4")


def test_unknown_loader_returns_404(client):
    resp = client.get("/api/loaders/wololo/versions/game")
    assert resp.status_code == 404
    assert "Unknown loader" in resp.get_json()["error"]


def test_game_versions_dispatch_to_vanilla(client):
    fake_versions = [
        {"version": "1.21.4", "stable": True, "type": "release"},
    ]
    with patch(
        "backend.server.installer.vanilla.VanillaInstaller.get_minecraft_versions",
        return_value=fake_versions,
    ):
        resp = client.get("/api/loaders/vanilla/versions/game")

    assert resp.status_code == 200
    assert resp.get_json() == fake_versions


def test_loader_versions_for_vanilla_is_empty(client):
    """Vanilla has no separate loader versions — endpoint returns []."""
    resp = client.get("/api/loaders/vanilla/versions/loader?mc_version=1.21.4")
    assert resp.status_code == 200
    assert resp.get_json() == []


def test_game_versions_dispatch_to_neoforge(client):
    fake_versions = [
        {"version": "1.21.1", "stable": True, "type": "release"},
        {"version": "1.21.0", "stable": False, "type": "snapshot"},
    ]
    with patch(
        "backend.server.installer.neoforge.NeoForgeInstaller.get_minecraft_versions",
        return_value=fake_versions,
    ):
        resp = client.get("/api/loaders/neoforge/versions/game")

    assert resp.status_code == 200
    assert resp.get_json() == fake_versions


def test_game_versions_dispatch_to_quilt(client):
    fake_versions = [
        {"version": "1.21.4", "stable": True, "type": "release"},
        {"version": "25w03a", "stable": False, "type": "snapshot"},
    ]
    with patch(
        "backend.server.installer.quilt.QuiltInstaller.get_minecraft_versions",
        return_value=fake_versions,
    ):
        resp = client.get("/api/loaders/quilt/versions/game")

    assert resp.status_code == 200
    assert resp.get_json() == fake_versions


def test_loader_versions_dispatch_to_quilt(client):
    fake = [{"version": "0.27.0", "stable": True, "type": "release"}]
    with patch(
        "backend.server.installer.quilt.QuiltInstaller.get_available_versions",
        return_value=fake,
    ) as mock:
        resp = client.get("/api/loaders/quilt/versions/loader?mc_version=1.21.4")

    assert resp.status_code == 200
    assert resp.get_json() == fake
    mock.assert_called_once_with("1.21.4")
