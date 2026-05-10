"""Application configuration.

Config is an *instance-based* object. `get_config()` constructs a fresh
instance on each call, which reads env vars at that moment. This avoids the
import-time snapshotting problem that historically made env overrides
(tests, `.env` loading ordering, `sys._MEIPASS`) not take effect.
"""
from __future__ import annotations

import os
from typing import List
from urllib.parse import urlparse

from backend.utils.platform import appdata_dir


def _parse_cors_origins(raw: str) -> List[str]:
    """Parse CORS_ORIGINS env as a comma-separated allowlist.

    Wildcards are rejected: they defeat the point of having an allowlist on
    destructive endpoints. Callers that genuinely want open access must list
    every origin explicitly.
    """
    cleaned = (raw or "").strip()
    if cleaned == "*":
        raise ValueError(
            "Wildcard CORS_ORIGINS='*' is not permitted. Set an explicit allowlist "
            "like 'http://localhost:3000,https://ui.example.com'."
        )
    origins = [part.strip() for part in cleaned.split(",") if part.strip()]
    if not origins:
        # Safe default for local dev: the Vite dev server origin.
        return ["http://localhost:3000"]
    for origin in origins:
        if not origin.startswith(("http://", "https://")):
            raise ValueError(
                f"CORS_ORIGINS entry '{origin}' must start with http:// or https://."
            )
        if not urlparse(origin).netloc:
            raise ValueError(
                f"CORS_ORIGINS entry '{origin}' has no host component."
            )
    return origins


class Config:
    """Base configuration. All env-derived values are set in __init__ so
    each get_config() call reflects current env state.
    """

    # Directory that `backend/core/config.py` is two levels under the repo
    # root. Falls back to sys._MEIPASS for PyInstaller builds.
    PROJECT_ROOT = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )

    def __init__(self) -> None:
        # Flask — loopback by default. Operators who want remote access must
        # set HOST explicitly (and should put Fabricator behind a reverse
        # proxy).
        self.DEBUG = os.environ.get("FLASK_ENV") != "production"
        self.HOST = os.environ.get("HOST", "127.0.0.1")
        self.PORT = int(os.environ.get("PORT", 5000))

        # Server management
        self.SERVERS_ROOT = os.environ.get(
            "SERVER_ROOT", self._default_servers_root()
        )
        self.SERVERS_FILE = os.environ.get(
            "SERVER_INDEX_FILE", self._default_servers_file()
        )
        self.JAVA_ROOT = os.environ.get(
            "JAVA_ROOT", self._default_java_root()
        )

        # CORS — parsed and validated at construction time. Raises ValueError
        # on '*' or on any entry that is not an http(s) origin.
        self.CORS_ORIGINS = _parse_cors_origins(
            os.environ.get("CORS_ORIGINS", "")
        )

    # Sub-classes override these to change defaults without duplicating env
    # handling. On Windows we always anchor data under %APPDATA%\Fabricator
    # so the .exe stays portable and data survives if the user moves it.
    def _default_servers_root(self) -> str:
        appdata = appdata_dir()
        if appdata is not None:
            return str(appdata / "servers")
        return os.path.join(os.getcwd(), "servers")

    def _default_servers_file(self) -> str:
        appdata = appdata_dir()
        if appdata is not None:
            return str(appdata / "servers.json")
        return os.path.join(self.PROJECT_ROOT, "servers.json")

    def _default_java_root(self) -> str:
        appdata = appdata_dir()
        if appdata is not None:
            return str(appdata / "java")
        return os.path.join(self.PROJECT_ROOT, "java")


class DevelopmentConfig(Config):
    """Development configuration."""

    def __init__(self) -> None:
        super().__init__()
        self.DEBUG = True


class ProductionConfig(Config):
    """Production configuration."""

    def __init__(self) -> None:
        super().__init__()
        self.DEBUG = False

    def _default_servers_root(self) -> str:
        return "/var/lib/fabricator/servers"

    def _default_servers_file(self) -> str:
        return "/var/lib/fabricator/servers.json"

    def _default_java_root(self) -> str:
        return "/var/lib/fabricator/java"


_CONFIG_CLASSES = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
}


def get_config() -> Config:
    """Return a fresh Config instance reflecting the current environment."""
    env = os.environ.get("FLASK_ENV", "development")
    config_cls = _CONFIG_CLASSES.get(env, DevelopmentConfig)
    return config_cls()
