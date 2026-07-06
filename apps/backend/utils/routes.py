"""Route decorators shared by server/modrinth blueprints.

Two decorators address the most common boilerplate in route handlers:

- :func:`require_server` resolves the ``<server_id>`` URL parameter to a
  server dict via :mod:`backend.server.storage` and returns a 404 if the
  id is unknown. The decorated view receives ``server`` as a kwarg.

- :func:`with_server_lock` acquires the per-server ``RLock`` from
  :mod:`backend.server.locks` and releases it after the view returns.
  Returns 409 if another operation already holds the lock.

Both decorators read ``server_id`` from the URL by default. Pass
``source='body'`` to read it from the JSON request body instead — useful
for endpoints like ``POST /api/modrinth/mod/<mod_id>/install`` where the
target server is supplied in the request payload, not the path.

Stacking convention
-------------------
``@require_server`` MUST sit above ``@with_server_lock``::

    @bp.route('/servers/<server_id>/foo', methods=['POST'])
    @require_server
    @with_server_lock
    def foo(server_id, server):
        ...

Reasoning: locking a non-existent server would create an entry in the
locks table for an id that will never see a release path. The 404 must
fire first.
"""
from __future__ import annotations

from functools import wraps
from typing import Callable

from flask import jsonify, request

# NOTE: ``backend.server.storage`` and ``backend.server.locks`` are
# imported lazily inside the wrappers — defensive lazy lookup. The current
# topology (``backend.core.app`` → ``backend.server.routes`` →
# ``backend.utils.routes`` → ``backend.server.storage``) has no actual
# cycle (``backend.server.__init__`` does not import this module back),
# but a local import keeps the contract safe against future re-orderings
# of the ``backend.server`` package or any of its consumers. The deferred
# lookup runs once per request and costs a dict lookup.


def _server_id_from(source: str, kwargs: dict) -> str | None:
    """Resolve a ``server_id`` from either the URL kwargs or the JSON body."""
    if source == 'url':
        return kwargs.get('server_id')
    if source == 'body':
        data = request.get_json(silent=True) or {}
        return data.get('server_id') if isinstance(data, dict) else None
    raise ValueError(f"Unknown source: {source!r}")


def require_server(view: Callable | None = None, *, source: str = 'url') -> Callable:
    """Resolve ``server_id`` to a server dict, 404 if missing.

    The wrapped view receives the resolved ``server`` dict as a keyword
    argument in addition to its existing parameters. Replaces the
    boilerplate::

        server = storage.get_server(server_id)
        if not server:
            return jsonify({'error': 'Server not found'}), 404

    With ``source='body'`` the id is pulled from ``request.get_json()``
    instead of URL kwargs; missing id returns 400.
    """

    def decorator(inner: Callable) -> Callable:
        @wraps(inner)
        def wrapper(*args, **kwargs):
            from backend.server import storage  # defensive lazy import; see module-level NOTE

            server_id = _server_id_from(source, kwargs)
            if source == 'body' and not server_id:
                return jsonify({'error': 'server_id is required'}), 400
            server = storage.get_server(server_id)
            if not server:
                return jsonify({'error': 'Server not found'}), 404
            return inner(*args, server=server, **kwargs)

        return wrapper

    # Allow bare-decorator usage: @require_server
    if view is not None and callable(view):
        return decorator(view)
    return decorator


def with_server_lock(
    view: Callable | None = None,
    *,
    source: str = 'url',
    busy_message: str = 'Another operation is in progress for this server',
) -> Callable:
    """Acquire the per-server lock; return 409 if held; auto-release on exit.

    Stacks below ``@require_server`` so the 404 path runs first.
    Replaces the boilerplate::

        lock = try_acquire(server_id)
        if lock is None:
            return jsonify({'error': busy_message}), 409
        try:
            ...
        finally:
            lock.release()

    With ``source='body'`` the id is pulled from ``request.get_json()``
    instead of URL kwargs.
    """

    def decorator(inner: Callable) -> Callable:
        @wraps(inner)
        def wrapper(*args, **kwargs):
            from backend.server.locks import try_acquire  # defensive lazy import; see module-level NOTE

            server_id = _server_id_from(source, kwargs)
            lock = try_acquire(server_id)
            if lock is None:
                return jsonify({'error': busy_message}), 409
            try:
                return inner(*args, **kwargs)
            finally:
                lock.release()

        return wrapper

    if view is not None and callable(view):
        return decorator(view)
    return decorator
