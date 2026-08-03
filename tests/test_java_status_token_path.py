"""``java_path`` is a caller-chosen binary the handler executes.

``GET /api/java/status`` probes ``java_path`` with ``subprocess.run``. That makes
a caller-supplied value arbitrary process execution reached from a READ route,
so the token path refuses it outright. The operator's own session keeps today's
behaviour byte-identical -- they already own the machine.
"""
from __future__ import annotations

from backend.auth import service


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


def _token(scope="read"):
    service.set_mcp_enabled(True)
    return service.create_token("t", scope)["token"]


def test_token_request_with_java_path_is_rejected(auth_client):
    resp = auth_client.get(
        "/api/java/status?java_path=C:\\Windows\\System32\\cmd.exe",
        headers=_bearer(_token()),
    )
    assert resp.status_code == 400
    assert "java_path" in resp.get_json()["error"]


def test_token_request_without_java_path_still_works(auth_client):
    resp = auth_client.get("/api/java/status", headers=_bearer(_token()))
    assert resp.status_code == 200


def test_java_path_never_reaches_the_probe_on_the_token_path(auth_client, monkeypatch):
    """The rejection happens before any process is spawned."""
    import subprocess

    def _explode(*args, **kwargs):  # pragma: no cover - must never run
        raise AssertionError(f"subprocess spawned on the token path: {args!r}")

    monkeypatch.setattr(subprocess, "run", _explode)
    resp = auth_client.get(
        "/api/java/status?java_path=/bin/sh", headers=_bearer(_token())
    )
    assert resp.status_code == 400


def test_session_request_with_java_path_is_unchanged(authed_client, monkeypatch):
    """Session callers keep the existing behaviour: the param is honoured."""
    probed = []
    import subprocess

    real_run = subprocess.run

    def _record(cmd, *args, **kwargs):
        probed.append(cmd)
        return real_run([__import__("sys").executable, "-c", ""], *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", _record)
    resp = authed_client.get("/api/java/status?java_path=my-java-binary")
    assert resp.status_code == 200
    assert any("my-java-binary" in str(cmd) for cmd in probed)
