"""What the manage tools put on the wire, and what they refuse to send."""
from __future__ import annotations

import httpx
import pytest

from fabricator_mcp.client import PanelClient
from fabricator_mcp.config import PanelConfig
from fabricator_mcp.tools import manage as manage_tools
from fabricator_mcp.tools.manage import NESTED_MOD_GUIDANCE

pytestmark = pytest.mark.anyio

_CONFIG = PanelConfig(url="http://panel.test:5000", token="fab_id_secret")


class Panel:
    def __init__(self, body: object | None = None, status: int = 200):
        self.requests: list[httpx.Request] = []
        self._body = body if body is not None else {}
        self._status = status
        self.transport = httpx.MockTransport(self._handle)

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return httpx.Response(self._status, json=self._body)

    @property
    def calls(self) -> list[tuple[str, str]]:
        return [(r.method, r.url.path) for r in self.requests]

    def body(self, index: int = 0):
        import json

        raw = self.requests[index].content
        return json.loads(raw) if raw else None


def client_for(panel: Panel) -> PanelClient:
    return PanelClient(_CONFIG, transport=panel.transport)


@pytest.mark.parametrize("action", ["start", "stop", "restart"])
async def test_control_server_maps_each_action_to_its_own_route(action):
    panel = Panel({"success": True, "message": "ok", "server": {"id": "s1"}})
    async with client_for(panel) as client:
        result = await manage_tools.control_server(client, "s1", action)
    assert panel.calls == [("POST", f"/api/servers/s1/{action}")]
    assert result["server"]["id"] == "s1"


async def test_control_server_rejects_an_unknown_action_before_any_request():
    panel = Panel()
    async with client_for(panel) as client:
        with pytest.raises(ValueError, match="start, stop, restart"):
            await manage_tools.control_server(client, "s1", "delete")
    assert panel.calls == []


async def test_control_server_response_is_projected():
    """The embedded record rides these responses; only the useful fields pass on."""
    panel = Panel({
        "success": True,
        "message": "started",
        "server": {"id": "s1", "status": "running", "motd": "noise", "difficulty": "hard"},
    })
    async with client_for(panel) as client:
        result = await manage_tools.control_server(client, "s1", "start")
    assert set(result["server"]) == {"id", "status"}


async def test_install_server_starts_the_panel_install_worker_without_a_body():
    panel = Panel({"active": True, "phase": "starting", "server_id": "s1", "loader": "paper", "mc_version": "1.21.4"})
    async with client_for(panel) as client:
        result = await manage_tools.install_server(client, "s1")
    assert panel.calls == [("POST", "/api/servers/s1/install")]
    assert panel.body() is None
    assert result == {
        "active": True,
        "phase": "starting",
        "serverId": "s1",
        "loader": "paper",
        "minecraftVersion": "1.21.4",
    }


async def test_update_or_install_mod_sends_the_required_body():
    panel = Panel({"success": True, "message": "Mod installed successfully", "file": "sodium.jar"})
    async with client_for(panel) as client:
        result = await manage_tools.update_or_install_mod(
            client, "s1", "AANobbMI", "1.20.1", "fabric"
        )
    assert panel.calls == [("POST", "/api/modrinth/mod/AANobbMI/install")]
    assert panel.body() == {"server_id": "s1", "mc_version": "1.20.1", "loader": "fabric"}
    assert result["file"] == "sodium.jar"


async def test_update_or_install_mod_never_sends_a_mods_folder_override():
    panel = Panel({"success": True})
    async with client_for(panel) as client:
        await manage_tools.update_or_install_mod(client, "s1", "AANobbMI", "1.20.1")
    assert "mods_folder" not in panel.body()


async def test_update_or_install_mod_requires_an_mc_version():
    panel = Panel()
    async with client_for(panel) as client:
        with pytest.raises(ValueError, match="mc_version"):
            await manage_tools.update_or_install_mod(client, "s1", "AANobbMI", "")
    assert panel.calls == []


async def test_removing_one_mod_uses_the_single_route():
    panel = Panel({"success": True, "message": "sodium.jar removed"})
    async with client_for(panel) as client:
        result = await manage_tools.remove_mods(client, "s1", ["sodium.jar"])
    assert panel.calls == [("DELETE", "/api/servers/s1/mods/sodium.jar")]
    assert result["deleted"] == ["sodium.jar"]


async def test_removing_several_mods_uses_the_bulk_route_with_a_body():
    panel = Panel({"success": True, "deleted": ["a.jar", "b.jar"], "errors": []})
    async with client_for(panel) as client:
        result = await manage_tools.remove_mods(client, "s1", ["a.jar", "b.jar"])
    assert panel.calls == [("DELETE", "/api/servers/s1/mods")]
    assert panel.body() == {"filenames": ["a.jar", "b.jar"]}
    assert result["deleted"] == ["a.jar", "b.jar"]


@pytest.mark.parametrize("name", ["nested/sodium.jar", "nested\\sodium.jar"])
async def test_a_nested_name_is_refused_with_the_panel_ui_guidance(name):
    """A4: the limitation is explained, not worked around."""
    panel = Panel()
    async with client_for(panel) as client:
        with pytest.raises(ValueError) as exc:
            await manage_tools.remove_mods(client, "s1", [name])
    assert NESTED_MOD_GUIDANCE in str(exc.value)
    assert "panel UI" in str(exc.value)
    assert panel.calls == []


@pytest.mark.parametrize("bad", [[], [""], ["  "], ["../escape.jar"], "  "])
async def test_unusable_filenames_are_refused_before_any_request(bad):
    panel = Panel()
    async with client_for(panel) as client:
        with pytest.raises(ValueError):
            await manage_tools.remove_mods(client, "s1", bad)
    assert panel.calls == []


async def test_too_many_filenames_are_refused():
    panel = Panel()
    async with client_for(panel) as client:
        with pytest.raises(ValueError, match="at most"):
            await manage_tools.remove_mods(client, "s1", [f"m{i}.jar" for i in range(51)])
    assert panel.calls == []
