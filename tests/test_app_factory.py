"""C5: Import-time side effects must be moved into create_app()."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path


def test_importing_routes_does_not_touch_disk(tmp_path, monkeypatch):
    """Importing backend.server.routes must not read or write servers.json."""
    monkeypatch.setenv("SERVER_ROOT", str(tmp_path / "servers"))
    monkeypatch.setenv("SERVER_INDEX_FILE", str(tmp_path / "index.json"))

    # Unload any cached modules from other tests.
    for mod in list(sys.modules):
        if mod.startswith("backend."):
            del sys.modules[mod]

    import backend.server.routes  # noqa: F401
    importlib.reload(backend.server.routes)

    assert not (tmp_path / "index.json").exists(), (
        "Importing routes must not create servers.json"
    )


def test_create_app_runs_stale_status_cleanup(tmp_servers_root):
    """Stale 'installing' statuses must flip to 'stopped' on create_app()."""
    # Seed a dirty servers.json before create_app runs.
    import json
    index = Path(tmp_servers_root) / "servers.json"
    index.write_text(
        json.dumps(
            [{"id": "srv_dirty", "name": "Dirty", "status": "installing"}]
        ),
        encoding="utf-8",
    )

    # Clear singleton + build app.
    import backend.server.registry as registry_mod
    registry_mod.reset_for_tests()
    from backend.core.app import create_app

    create_app()

    # Cleanup should have overwritten status.
    with open(index, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    assert data[0]["status"] == "stopped"


def test_registry_lazy_until_used(tmp_servers_root):
    """The registry singleton must not exist until something asks for it."""
    import backend.server.registry as registry_mod
    registry_mod.reset_for_tests()

    # Import routes module — should not construct the registry.
    for mod in list(sys.modules):
        if mod.startswith("backend.server.routes"):
            del sys.modules[mod]
    import backend.server.routes  # noqa: F401

    assert registry_mod._registry is None, (
        "Registry must be constructed lazily, not at import time"
    )
