"""Shared pytest fixtures for Fabricator tests."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make backend importable without installing the package.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture
def tmp_servers_root(tmp_path, monkeypatch):
    """Redirect SERVERS_ROOT + SERVER_INDEX_FILE + JAVA_ROOT to a temp dir.

    After Task 1, Config reads env vars at instance construction time, so
    monkeypatch.setenv alone is sufficient — no direct attribute writes.
    """
    servers_root = tmp_path / "servers"
    servers_root.mkdir()
    monkeypatch.setenv("SERVER_ROOT", str(servers_root))
    monkeypatch.setenv("SERVER_INDEX_FILE", str(tmp_path / "servers.json"))
    monkeypatch.setenv("JAVA_ROOT", str(tmp_path / "java"))
    monkeypatch.setenv("FLASK_ENV", "development")
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:3000")
    monkeypatch.setenv("HOST", "127.0.0.1")
    yield tmp_path


@pytest.fixture
def app(tmp_servers_root):
    """Return a Flask app configured against the temp servers root."""
    # Clear the registry singleton between tests.
    import backend.server.registry as registry_mod
    registry_mod._registry = None

    from backend.core.app import create_app
    app = create_app()
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client(app):
    """Flask test client."""
    return app.test_client()
