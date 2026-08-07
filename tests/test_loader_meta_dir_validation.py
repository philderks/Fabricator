"""An unknown loader must not create a directory named after the request.

The loader-versions routes name a metadata staging directory after the
``<loader>`` path segment and create it with ``mkdir(parents=True)``. That has to
happen after the loader is known-good, not before -- building a filesystem path
out of an unvalidated request segment is wrong regardless of which caller asked,
so this fix is global rather than token-scoped.
"""
from __future__ import annotations

from pathlib import Path

import pytest

import backend.server.routes as routes_mod
from backend.server.installer import supported_loaders

_ROUTES = (
    "/api/loaders/{loader}/versions/game",
    "/api/loaders/{loader}/versions/loader",
)

# A plain unknown name, and a Windows-style traversal that survives Flask's
# string converter (which only excludes "/").
_BAD_LOADERS = ("evil", "..%5C..%5Cevil", "")


@pytest.fixture
def no_temp_dirs(monkeypatch):
    """Record every temp_directory() call instead of creating anything."""
    calls = []

    def _record(name=None, *args, **kwargs):
        calls.append(name)
        return Path(".")

    monkeypatch.setattr(routes_mod.platform_utils, "temp_directory", _record)
    # _loader_meta_dir is lru_cached for process lifetime; without clearing it a
    # previous test's entry would hide the call this one is asserting on.
    routes_mod._loader_meta_dir.cache_clear()
    yield calls
    routes_mod._loader_meta_dir.cache_clear()


@pytest.mark.parametrize("route", _ROUTES)
@pytest.mark.parametrize("loader", _BAD_LOADERS)
def test_unknown_loader_creates_no_directory(client, no_temp_dirs, route, loader):
    resp = client.get(route.format(loader=loader))
    assert resp.status_code == 404
    assert no_temp_dirs == [], f"built a path from an unvalidated loader: {no_temp_dirs}"


# The positive direction is asserted against the guard itself rather than over
# HTTP: driving a real loader through the endpoint reaches the live upstream
# metadata API, and _loader_meta_dir is lru_cached for process lifetime, so a
# "was the directory built?" assertion would depend on whether some earlier test
# had already warmed that cache.

def test_validated_loader_accepts_every_registered_loader():
    """The guard must not reject a loader the installer registry can resolve."""
    for name in supported_loaders():
        assert routes_mod._validated_loader(name) == name
        assert routes_mod._validated_loader(name.upper()) == name
        assert routes_mod._validated_loader(f"  {name}  ") == name


@pytest.mark.parametrize("bad", ["evil", "..\\..\\evil", "../../evil", "", "   ", None])
def test_validated_loader_rejects_anything_unregistered(bad):
    assert routes_mod._validated_loader(bad) is None
