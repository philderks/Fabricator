"""Host paths hidden inside error strings, not inside field names.

The key filter drops fields by name and never looks inside a string value. The
progress/task stores carry Python exception text, and an exception that failed
on a file quotes that file's absolute path. This is the second, separate
mechanism that covers that surface -- and only on the token path; the operator's
session still sees the real path it needs to fix the problem.
"""
from __future__ import annotations


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


def _token(scope="read"):
    # Imported inside the call, not at module import: tests/test_app_factory.py
    # purges every "backend.*" entry from sys.modules, so a reference bound at
    # import time can end up pointing at a stale module object whose
    # process-wide stores the running app no longer uses. conftest.py imports
    # inside its fixtures for the same reason.
    from backend.auth import service

    service.set_mcp_enabled(True)
    return service.create_token("t", scope)["token"]


def _seed_failed_install(tmp_servers_root):
    """A server whose install failed with an absolute path in the error text."""
    from backend.server import install_progress, storage

    server = storage.create_server({"name": "s", "version": "1.20.1", "loader": "vanilla"})
    root = str(tmp_servers_root / "servers")
    install_progress.update(
        server["id"],
        phase="failed",
        error=f"could not write {root}/{server['id']}/mods/sodium.jar",
    )
    return server["id"], root


def test_token_response_scrubs_host_path_from_error_string(auth_client, tmp_servers_root):
    server_id, root = _seed_failed_install(tmp_servers_root)

    resp = auth_client.get(
        f"/api/servers/{server_id}/install/progress", headers=_bearer(_token())
    )

    # Assert on the PARSED value: JSON escapes backslashes, so a raw-text
    # substring check for a Windows path would pass whether or not it worked.
    error = resp.get_json()["error"]
    assert resp.status_code == 200
    assert root not in error, "host root leaked inside an error string"
    assert "<path>" in error


def test_the_useful_tail_of_the_path_survives(auth_client, tmp_servers_root):
    """Scrubbing removes host layout, not the filename diagnosis needs."""
    server_id, _ = _seed_failed_install(tmp_servers_root)

    resp = auth_client.get(
        f"/api/servers/{server_id}/install/progress", headers=_bearer(_token())
    )

    assert "sodium.jar" in resp.get_json()["error"]


def test_session_response_keeps_the_real_path(authed_client, tmp_servers_root):
    """Session behaviour is unchanged: the operator sees the actual path."""
    server_id, root = _seed_failed_install(tmp_servers_root)

    resp = authed_client.get(f"/api/servers/{server_id}/install/progress")

    assert resp.status_code == 200
    assert root in resp.get_json()["error"]
