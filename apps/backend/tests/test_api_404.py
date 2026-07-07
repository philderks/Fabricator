"""Tests for the JSON-404 fallback on unknown /api/... routes (B15.6b).

The SPA catch-all at `/<path:path>` should still own non-API routes (returns
HTML or 503 if frontend not built), but `/api/...` paths must return a
machine-readable JSON 404 rather than the SPA's HTML — clients consuming
the API should not have to parse HTML to detect a missing endpoint.
"""
from __future__ import annotations


def test_api_unknown_get_returns_json_404(client):
    response = client.get('/api/nonexistent')
    assert response.status_code == 404
    assert response.is_json
    body = response.get_json()
    assert body['error'] == 'endpoint not found'
    assert body['path'] == '/api/nonexistent'


def test_api_unknown_post_returns_json_404(client):
    response = client.post('/api/nonexistent')
    assert response.status_code == 404
    assert response.is_json
    body = response.get_json()
    assert body['error'] == 'endpoint not found'
    assert body['path'] == '/api/nonexistent'


def test_spa_unknown_does_not_return_api_404(client):
    """Non-API routes must still hit the SPA catch-all, not the api-404 fallback.

    In a built-frontend env returns 200 + index.html; in a bare test env
    returns 503 JSON. Either is acceptable; what's NOT acceptable is a 404
    with the api_not_found JSON body.
    """
    response = client.get('/some-spa-route')
    assert response.status_code != 404
    body = response.get_json(silent=True)
    if body is not None:
        assert body.get('error') != 'endpoint not found'
