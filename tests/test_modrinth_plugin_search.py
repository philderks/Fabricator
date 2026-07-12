"""Plugin-aware Modrinth search route + facet-list resolve."""
from __future__ import annotations

from unittest.mock import patch


def test_search_defaults_to_mod_project_type(client, tmp_servers_root):
    with patch("backend.modrinth.routes.modrinth_client.search") as mock_search:
        mock_search.return_value = {"hits": []}
        resp = client.get("/api/modrinth/search?query=sodium&loader=fabric")
    assert resp.status_code == 200
    assert mock_search.call_args.kwargs["project_type"] == "mod"


def test_search_accepts_plugin_project_type(client, tmp_servers_root):
    with patch("backend.modrinth.routes.modrinth_client.search") as mock_search:
        mock_search.return_value = {"hits": []}
        resp = client.get(
            "/api/modrinth/search?query=essentials&loader=&project_type=plugin"
        )
    assert resp.status_code == 200
    assert mock_search.call_args.kwargs["project_type"] == "plugin"


def test_search_rejects_bogus_project_type(client, tmp_servers_root):
    """A bad project_type must fall back to 'mod', never reshape the facet."""
    with patch("backend.modrinth.routes.modrinth_client.search") as mock_search:
        mock_search.return_value = {"hits": []}
        resp = client.get(
            "/api/modrinth/search?query=x&project_type=datapack"
        )
    assert resp.status_code == 200
    assert mock_search.call_args.kwargs["project_type"] == "mod"


def test_install_uses_server_loader_facets_for_paper(client, tmp_servers_root):
    """A Paper server resolves plugins against the paper/spigot/bukkit chain."""
    from backend.server import storage

    server = storage.create_server({
        "name": "Pap",
        "version": "1.21.4",
        "loader": "paper",
        "port": 25599,
        "installPath": "srv-paper",
        "memory": 4,
    })

    with patch(
        "backend.modrinth.routes.modrinth_client.get_project_download_url"
    ) as mock_resolve, patch(
        "backend.modrinth.routes.modrinth_client.download_mod"
    ) as mock_download:
        mock_resolve.return_value = {
            "url": "https://example.invalid/plugin.jar",
            "hashes": {},
        }
        mock_download.return_value = type("P", (), {"name": "plugin.jar"})()
        resp = client.post(
            "/api/modrinth/mod/SOMEPLUGIN/install",
            json={
                "server_id": server["id"],
                "mc_version": "1.21.4",
                "loader": "paper",
            },
        )

    assert resp.status_code == 200, resp.get_json()
    assert mock_resolve.call_args.kwargs["loaders"] == ["paper", "spigot", "bukkit"]
    # Plugin jars land in plugins/, not mods/.
    target_folder = mock_download.call_args.args[1]
    assert target_folder.name == "plugins"
