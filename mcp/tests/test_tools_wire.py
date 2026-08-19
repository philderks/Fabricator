"""What each tool actually puts on the wire.

The route table says which routes a tool may call; these assert what it really
does call, so the table cannot drift away from the code without something going
red.
"""
from __future__ import annotations

import httpx
import pytest

from fabricator_mcp.client import PanelClient
from fabricator_mcp.config import PanelConfig
from fabricator_mcp.tools import read as read_tools

pytestmark = pytest.mark.anyio

_CONFIG = PanelConfig(url="http://panel.test:5000", token="fab_id_secret")


class Panel:
    """A mock panel that records requests and answers from a routing table."""

    def __init__(self, responses: dict[str, object] | None = None):
        self.requests: list[httpx.Request] = []
        self._responses = responses or {}
        self.transport = httpx.MockTransport(self._handle)

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        body = self._responses.get(request.url.path, {})
        if isinstance(body, int):
            return httpx.Response(body, json={"error": "no suitable version found"})
        return httpx.Response(200, json=body)

    @property
    def calls(self) -> list[tuple[str, str]]:
        return [(r.method, r.url.path) for r in self.requests]

    def query(self, index: int = 0) -> dict[str, str]:
        return dict(self.requests[index].url.params)


def client_for(panel: Panel) -> PanelClient:
    return PanelClient(_CONFIG, transport=panel.transport)


async def test_list_servers_hits_exactly_one_route():
    panel = Panel({"/api/servers": [{"id": "s1", "name": "a"}]})
    async with client_for(panel) as client:
        result = await read_tools.list_servers(client)
    assert panel.calls == [("GET", "/api/servers")]
    assert result["servers"][0]["id"] == "s1"


async def test_get_server_uses_the_id_in_the_path():
    panel = Panel({"/api/servers/s1": {"id": "s1"}})
    async with client_for(panel) as client:
        await read_tools.get_server(client, "s1")
    assert panel.calls == [("GET", "/api/servers/s1")]


@pytest.mark.parametrize("bad", ["", "   ", "a/b", "a\\b"])
async def test_server_id_with_a_separator_is_rejected_before_any_request(bad):
    panel = Panel()
    async with client_for(panel) as client:
        with pytest.raises(ValueError):
            await read_tools.get_server(client, bad)
    assert panel.calls == []


async def test_read_server_logs_sends_a_clamped_limit():
    panel = Panel({"/api/servers/s1/logs": {"running": True, "stdout": [], "stderr": []}})
    async with client_for(panel) as client:
        await read_tools.read_server_logs(client, "s1", limit=99999)
    assert panel.calls == [("GET", "/api/servers/s1/logs")]
    assert panel.query() == {"limit": "1000"}


async def test_list_installed_mods_makes_one_request_by_default():
    panel = Panel({"/api/servers/s1/mods": [{"name": "sodium.jar", "size": 10}]})
    async with client_for(panel) as client:
        result = await read_tools.list_installed_mods(client, "s1")
    assert panel.calls == [("GET", "/api/servers/s1/mods")]
    assert result["identified"] is False


async def test_list_installed_mods_identify_makes_two_requests_and_merges():
    panel = Panel({
        "/api/servers/s1/mods": [{"name": "sodium.jar"}, {"name": "mystery.jar"}],
        "/api/modrinth/servers/s1/resolve-installed": {
            "resolved": {"mystery.jar": {"projectId": "AANobbMI", "title": "Sodium"}}
        },
    })
    async with client_for(panel) as client:
        result = await read_tools.list_installed_mods(client, "s1", identify=True)

    assert panel.calls == [
        ("GET", "/api/servers/s1/mods"),
        ("GET", "/api/modrinth/servers/s1/resolve-installed"),
    ]
    assert result["identified"] is True
    by_name = {mod["name"]: mod for mod in result["mods"]}
    assert by_name["mystery.jar"]["projectId"] == "AANobbMI"
    assert by_name["mystery.jar"]["source"] == "hash"


async def test_check_resource_usage_hits_both_metric_routes():
    panel = Panel({
        "/api/servers/s1/metrics": {"status": "running", "ram": 2048, "pid": 42},
        "/api/metrics/system": {"cpu": {"percent": 12.5}, "memory": {"percent": 40}},
    })
    async with client_for(panel) as client:
        result = await read_tools.check_resource_usage(client, "s1")
    assert panel.calls == [("GET", "/api/servers/s1/metrics"), ("GET", "/api/metrics/system")]
    assert result["server"]["ram"] == 2048
    assert result["host"]["cpuPercent"] == 12.5


async def test_check_java_never_sends_java_path():
    """The parameter that used to be an arbitrary-execution vector."""
    panel = Panel({"/api/java/status": {"required_java": 17}, "/api/java/installed": {}})
    async with client_for(panel) as client:
        await read_tools.check_java(client, mc_version="1.20.1")

    assert panel.calls == [("GET", "/api/java/status"), ("GET", "/api/java/installed")]
    assert panel.query() == {"mc_version": "1.20.1"}
    assert "java_path" not in panel.query()


async def test_check_java_without_a_version_sends_no_params():
    panel = Panel({"/api/java/status": {}, "/api/java/installed": {}})
    async with client_for(panel) as client:
        await read_tools.check_java(client)
    assert panel.query() == {}


async def test_list_loader_game_versions_uses_the_loader_metadata_route():
    panel = Panel({"/api/loaders/paper/versions/game": [
        {"version": "1.21.4", "stable": True, "type": "release", "noise": "drop"},
    ]})
    async with client_for(panel) as client:
        result = await read_tools.list_loader_game_versions(client, "paper")
    assert panel.calls == [("GET", "/api/loaders/paper/versions/game")]
    assert result == {"loader": "paper", "minecraftVersions": [
        {"version": "1.21.4", "stable": True, "type": "release"},
    ]}


async def test_list_loader_versions_sends_an_optional_minecraft_version():
    panel = Panel({"/api/loaders/paper/versions/loader": [
        {"loader": {"version": "0.16.0", "stable": True}, "noise": "drop"},
    ]})
    async with client_for(panel) as client:
        result = await read_tools.list_loader_versions(client, "paper", "1.21.4")
    assert panel.calls == [("GET", "/api/loaders/paper/versions/loader")]
    assert panel.query() == {"mc_version": "1.21.4"}
    assert result == {"loader": "paper", "minecraftVersion": "1.21.4", "versions": [
        {"version": "0.16.0", "stable": True},
    ]}


async def test_get_backup_status_projects_summary_without_its_storage_path():
    panel = Panel({"/api/servers/s1/backup-summary": {
        "total_snapshots": 3,
        "total_size_bytes": 1234,
        "last_snapshot": {"id": "snap-1", "fileName": "safe.tar", "filePath": "/srv/secrets"},
        "next_run": {"config_id": "nightly", "config_name": "Nightly", "next_run_time": "2026-08-20T01:00:00Z"},
        "configs_count": 1,
        "defaultStoragePath": "/srv/fabricator/backups",
    }})
    async with client_for(panel) as client:
        result = await read_tools.get_backup_status(client, "s1")
    assert panel.calls == [("GET", "/api/servers/s1/backup-summary")]
    assert result == {
        "totalSnapshots": 3,
        "totalSizeBytes": 1234,
        "lastSnapshot": {"id": "snap-1", "fileName": "safe.tar"},
        "nextRun": {"configId": "nightly", "configName": "Nightly", "nextRunTime": "2026-08-20T01:00:00Z"},
        "configsCount": 1,
    }
    assert "srv" not in str(result)


async def test_list_snapshots_projects_recovery_metadata_without_file_paths():
    panel = Panel({"/api/servers/s1/snapshots": [{
        "id": "snap-1", "type": "backup", "createdAt": "2026-08-19T00:00:00Z",
        "fileName": "before-upgrade.tar", "filePath": "/srv/fabricator/backups/before-upgrade.tar",
        "sizeBytes": 1234, "status": "success",
    }]})
    async with client_for(panel) as client:
        result = await read_tools.list_snapshots(client, "s1")
    assert panel.calls == [("GET", "/api/servers/s1/snapshots")]
    assert result == {"snapshots": [{
        "id": "snap-1", "type": "backup", "createdAt": "2026-08-19T00:00:00Z",
        "fileName": "before-upgrade.tar", "sizeBytes": 1234, "status": "success",
    }]}
    assert "srv" not in str(result)


async def test_get_install_progress_route_and_error_field():
    panel = Panel({"/api/servers/s1/install/progress": {"active": False, "phase": "failed", "error": "boom"}})
    async with client_for(panel) as client:
        result = await read_tools.get_install_progress(client, "s1")
    assert panel.calls == [("GET", "/api/servers/s1/install/progress")]
    assert result["error"] == "boom"


async def test_check_panel_hits_health_and_status():
    panel = Panel({
        "/api/health": {"healthy": True},
        "/api/auth/status": {"managed": False, "needs_setup": False},
    })
    async with client_for(panel) as client:
        result = await read_tools.check_panel(client)
    assert panel.calls == [("GET", "/api/health"), ("GET", "/api/auth/status")]
    assert result["reachable"] is True


async def test_check_panel_reports_a_real_version():
    panel = Panel({
        "/api/health": {"healthy": True},
        "/api/auth/status": {"managed": False, "needs_setup": False, "panel_version": "v1.0.3"},
    })
    async with client_for(panel) as client:
        result = await read_tools.check_panel(client)
    assert result["panelVersion"] == "v1.0.3"
    assert "panelVersionKnown" not in result


@pytest.mark.parametrize(
    "status_body",
    [
        {"managed": False, "needs_setup": False, "panel_version": "unknown"},
        {"managed": False, "needs_setup": False, "panel_version": ""},
        {"managed": False, "needs_setup": False},  # panel older than the field
    ],
)
async def test_check_panel_does_not_pass_off_a_non_version_as_a_version(status_body):
    """"unknown" is not a version, and a missing field is not a check."""
    panel = Panel({"/api/health": {"healthy": True}, "/api/auth/status": status_body})
    async with client_for(panel) as client:
        result = await read_tools.check_panel(client)

    assert "panelVersion" not in result
    assert result["panelVersionKnown"] is False
    assert "no version check was made" in result["panelVersionNote"]


async def test_search_modrinth_sends_the_query_and_clamped_limit():
    panel = Panel({"/api/modrinth/search": {"hits": [{"project_id": "AANobbMI", "title": "Sodium"}]}})
    async with client_for(panel) as client:
        result = await read_tools.search_modrinth(client, "sodium", limit=500)
    assert panel.calls == [("GET", "/api/modrinth/search")]
    assert panel.query()["query"] == "sodium"
    assert panel.query()["limit"] == "50"
    assert result["results"][0]["projectId"] == "AANobbMI"


async def test_get_mod_info_hits_project_and_versions():
    panel = Panel({
        "/api/modrinth/project/sodium": {"id": "AANobbMI", "title": "Sodium"},
        "/api/modrinth/project/sodium/versions": [
            {"id": "v1", "version_number": "0.5", "game_versions": ["1.20.1"], "loaders": ["fabric"]}
        ],
    })
    async with client_for(panel) as client:
        result = await read_tools.get_mod_info(client, "sodium")
    assert panel.calls == [
        ("GET", "/api/modrinth/project/sodium"),
        ("GET", "/api/modrinth/project/sodium/versions"),
    ]
    assert result["versions"][0]["loaders"] == ["fabric"]


async def test_check_mod_compatibility_requires_mc_version_before_any_request():
    panel = Panel()
    async with client_for(panel) as client:
        with pytest.raises(ValueError):
            await read_tools.check_mod_compatibility(client, "sodium", "")
    assert panel.calls == []


async def test_check_mod_compatibility_404_is_the_answer_not_a_fault():
    panel = Panel({"/api/modrinth/project/sodium/resolve-version": 404})
    async with client_for(panel) as client:
        result = await read_tools.check_mod_compatibility(client, "sodium", "1.21", "fabric")
    assert result["compatible"] is False
    assert "1.21" in result["reason"]


async def test_check_mod_compatibility_success_shape():
    panel = Panel({
        "/api/modrinth/project/sodium/resolve-version": {
            "version": {"id": "v9", "version_number": "0.6.0"}
        }
    })
    async with client_for(panel) as client:
        result = await read_tools.check_mod_compatibility(client, "sodium", "1.20.1")
    assert panel.query() == {"mc_version": "1.20.1"}
    assert result == {"compatible": True, "versionId": "v9", "versionNumber": "0.6.0"}


async def test_identification_failure_still_returns_the_mod_list():
    """Partial success is reported, not silently dropped."""
    class Flaky(Panel):
        def _handle(self, request):
            self.requests.append(request)
            if request.url.path.endswith("resolve-installed"):
                return httpx.Response(429, json={"error": "rate limited", "retry_after": 0})
            return httpx.Response(200, json=[{"name": "sodium.jar"}])

    panel = Flaky()
    async with PanelClient(_CONFIG, transport=panel.transport, sleep=_instant) as client:
        result = await read_tools.list_installed_mods(client, "s1", identify=True)

    assert result["identified"] is False
    assert "identificationError" in result
    assert result["mods"][0]["name"] == "sodium.jar"


async def _instant(_seconds: float) -> None:
    return None
