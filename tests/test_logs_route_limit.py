"""Limit handling on GET /api/servers/<id>/logs.

The console window was served at 200 lines while the manager buffered 10_000,
so ~2% of retained output was reachable and a modded startup scrolled itself
out of view. The default is now 1000, and the parameter is clamped: Flask's
``type=int`` yields None on unparseable input, and a bare ``entries[-0:]``
slice would return everything rather than nothing.
"""
from __future__ import annotations

import pytest

from backend.server.manager import ServerManager


@pytest.fixture
def route(app, monkeypatch):
    """Stub the registry and record the limit the route forwards to it.

    Patches the globals the *registered view* resolves from rather than a
    freshly imported ``backend.server.routes``: test_app_factory.py drops
    ``backend.*`` from sys.modules and reloads the routes module, so a plain
    import here can hand back a different module object than the one backing
    the live view, and the patch would land on the wrong globals.
    """
    seen = {}

    class _StubRegistry:
        def get_logs(self, server_id, limit):
            seen['limit'] = limit
            return {'stdout': [], 'stderr': [], 'running': False}

    view = app.view_functions['server.get_server_logs']
    monkeypatch.setitem(view.__globals__, '_registry', lambda: _StubRegistry())

    class _Route:
        limit_seen = staticmethod(lambda: seen['limit'])
        default = view.__globals__['_LOG_DEFAULT_LIMIT']

    return _Route


def test_default_limit_is_1000(client, route):
    response = client.get('/api/servers/srv_x/logs')
    assert response.status_code == 200
    assert route.limit_seen() == route.default == 1000


def test_explicit_limit_is_honoured(client, route):
    client.get('/api/servers/srv_x/logs?limit=250')
    assert route.limit_seen() == 250


def test_limit_clamped_to_buffer_size(client, route):
    """Asking past what the manager retains can't return more lines."""
    client.get('/api/servers/srv_x/logs?limit=999999')
    assert route.limit_seen() == ServerManager.MAX_LOG_LINES


def test_unparseable_limit_falls_back_to_default(client, route):
    """The Refresh button used to send the MouseEvent as `limit`; type=int
    turns that into None, which must not reach the slice."""
    client.get('/api/servers/srv_x/logs?limit=%5Bobject%20MouseEvent%5D')
    assert route.limit_seen() == route.default


@pytest.mark.parametrize('value', ['0', '-5'])
def test_non_positive_limit_falls_back_to_default(client, route, value):
    client.get(f'/api/servers/srv_x/logs?limit={value}')
    assert route.limit_seen() == route.default
