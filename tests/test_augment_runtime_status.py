"""GET /api/servers/<id> must not downgrade in-flight statuses.

Regression test for the bug where _augment_with_runtime overwrote a
persisted 'installing' status with 'stopped' (because the runtime
registry has no ServerManager for an un-installed server). The
frontend then thought the install was finished while the install
handler was still holding the per-server lock — clicks on Start /
Delete returned 409 "Another operation is in progress for this
server".

The runtime registry can only authoritatively claim 'running' or
'stopped'. Any other persisted state (pending, installing, starting,
stopping, failed) is owned by an active route handler and must not
be touched by status reconciliation.
"""
from __future__ import annotations

import pytest


@pytest.mark.parametrize("in_flight_status", [
    "pending",
    "installing",
    "starting",
    "stopping",
    "failed",
])
def test_get_server_does_not_downgrade_in_flight_status(
    client, tmp_servers_root, in_flight_status
):
    """A poll while a route handler holds an in-flight status must not flip it."""
    from backend.server import storage
    server = storage.create_server({
        "name": "InFlight",
        "version": "1.21.1",
        "loader": "neoforge",
        "port": 25500,
        "installPath": "inflight",
        "memory": 2,
    })
    server_id = server["id"]
    storage.update_server_status(server_id, in_flight_status)

    response = client.get(f"/api/servers/{server_id}")
    assert response.status_code == 200
    body = response.get_json()
    # The augmented response keeps the in-flight status the route owns.
    assert body["status"] == in_flight_status
    # Storage still holds the in-flight status — not silently flipped.
    assert storage.get_server(server_id)["status"] == in_flight_status


def test_get_server_does_reconcile_running_to_stopped(client, tmp_servers_root):
    """When persisted is 'running' but runtime says 'stopped' (e.g. crash),
    the augment helper still reconciles. This is the legitimate use case
    the regression must NOT break."""
    from backend.server import storage
    server = storage.create_server({
        "name": "Crashed",
        "version": "1.21.1",
        "loader": "fabric",
        "port": 25501,
        "installPath": "crashed",
        "memory": 2,
    })
    server_id = server["id"]
    storage.update_server_status(server_id, "running")  # stale 'running'

    response = client.get(f"/api/servers/{server_id}")
    assert response.status_code == 200
    body = response.get_json()
    # Registry has no manager → reports 'stopped'. Reconciliation kicks in
    # because persisted was 'running' (a runtime-knowable state).
    assert body["status"] == "stopped"
    assert storage.get_server(server_id)["status"] == "stopped"
