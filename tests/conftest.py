"""Shared pytest fixtures for Fabricator tests."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make backend importable without installing the package.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def _clear_platform_caches():
    """Reset platform-level ``lru_cache``s before each test.

    ``appdata_dir``, ``arch_label``, and ``_system_name`` are cached for
    process-lifetime. Tests that monkey-patch HOME, APPDATA,
    FABRICATOR_APPDATA, or the platform-name need a clean slate; without
    this fixture a stale cache from a previous test could leak into the
    next one and silently produce wrong paths or arch labels.
    """
    from backend.utils.platform import appdata_dir, arch_label, _system_name
    appdata_dir.cache_clear()
    arch_label.cache_clear()
    _system_name.cache_clear()
    yield
    appdata_dir.cache_clear()
    arch_label.cache_clear()
    _system_name.cache_clear()


@pytest.fixture
def tmp_servers_root(tmp_path, monkeypatch):
    """Redirect server/index/java roots to a temp dir.

    Sets the env vars ``SERVER_ROOT`` (-> ``Config.SERVERS_ROOT``),
    ``SERVER_INDEX_FILE`` (-> ``Config.SERVERS_FILE``) and ``JAVA_ROOT``
    (-> ``Config.JAVA_ROOT``). The env-var name and the Python attribute
    differ for ``SERVER_ROOT``/``SERVERS_ROOT`` — see ``core/config.py``.

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
    # Built-in auth is on by default and always fail-closed; the vast majority
    # of tests don't exercise it, so disable it here. Auth tests opt back in via
    # the auth_app/auth_client/authed_client fixtures below.
    monkeypatch.setenv("FABRICATOR_DISABLE_AUTH", "1")
    yield tmp_path


@pytest.fixture
def app(tmp_servers_root):
    """Return a Flask app configured against the temp servers root."""
    # Clear the registry singleton between tests.
    import backend.server.registry as registry_mod
    registry_mod.reset_for_tests()

    from backend.core.app import create_app
    app = create_app()
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client(app):
    """Flask test client."""
    return app.test_client()


# Known password used by the auth fixtures.
_AUTH_TEST_PASSWORD = "s3cret-test-pw"


@pytest.fixture
def auth_app(tmp_servers_root, monkeypatch):
    """Flask app with built-in auth ENABLED and fully configured."""
    from backend.auth import service

    monkeypatch.delenv("FABRICATOR_DISABLE_AUTH", raising=False)
    monkeypatch.setenv("SECRET_KEY", "test-secret-key")
    monkeypatch.setenv(
        "FABRICATOR_AUTH_PASSWORD_HASH", service.hash_password(_AUTH_TEST_PASSWORD)
    )

    import backend.server.registry as registry_mod
    registry_mod.reset_for_tests()
    from backend.core.app import create_app

    app = create_app()
    app.config["TESTING"] = True
    return app


@pytest.fixture
def auth_client(auth_app):
    return auth_app.test_client()


@pytest.fixture
def authed_client(auth_client):
    """A client that has already logged in (carries the session cookie)."""
    resp = auth_client.post("/api/auth/login", json={"password": _AUTH_TEST_PASSWORD})
    assert resp.status_code == 200
    return auth_client
