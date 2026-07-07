"""SECRET_KEY must flow from env into app.config (Flask-standard name)."""
from __future__ import annotations


def test_secret_key_flows_to_app_config(tmp_servers_root, monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "test-secret-value")
    monkeypatch.setenv("FABRICATOR_DISABLE_AUTH", "1")  # so the app boots regardless of auth

    import backend.server.registry as registry_mod
    registry_mod.reset_for_tests()
    from backend.core.app import create_app

    app = create_app()
    assert app.config["SECRET_KEY"] == "test-secret-value"
