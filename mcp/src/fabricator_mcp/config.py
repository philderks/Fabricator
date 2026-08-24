"""Runtime configuration, read from the environment and nowhere else.

The panel URL and the API token arrive as environment variables set by the MCP
client on the process it spawns. The token is NEVER accepted on the command
line: ``argv`` is readable by every process on the machine (``/proc/<pid>/cmdline``,
``ps``, ``Get-CimInstance Win32_Process``) and it lands in shell history. A
child process's environment is neither.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlsplit

#: Where a self-hosted panel listens by default.
DEFAULT_URL = "http://127.0.0.1:5000"

URL_ENV = "FABRICATOR_URL"
TOKEN_ENV = "FABRICATOR_TOKEN"

_ALLOWED_SCHEMES = ("http", "https")


class ConfigError(RuntimeError):
    """The process cannot start with the configuration it was given.

    Raised before any tool is advertised: failing loudly at startup beats every
    tool failing opaquely later. The message is written for the person editing
    their client's config file, and never contains the token.
    """


@dataclass(frozen=True)
class PanelConfig:
    """Resolved settings for talking to one panel."""

    url: str
    token: str

    @classmethod
    def from_env(cls, env: "os._Environ[str] | dict[str, str] | None" = None) -> "PanelConfig":
        source = os.environ if env is None else env

        token = (source.get(TOKEN_ENV) or "").strip()
        if not token:
            raise ConfigError(
                f"{TOKEN_ENV} is not set. Create an API token in the panel's "
                f"Settings, under Model Context Protocol, and put it in the "
                f"\"env\" block of your MCP client configuration."
            )

        raw_url = (source.get(URL_ENV) or "").strip() or DEFAULT_URL
        url = raw_url.rstrip("/")
        parts = urlsplit(url)
        if parts.scheme not in _ALLOWED_SCHEMES or not parts.netloc:
            raise ConfigError(
                f"{URL_ENV} is not a valid http(s) URL: {raw_url!r}. "
                f"Use something like {DEFAULT_URL}."
            )

        return cls(url=url, token=token)

    def __repr__(self) -> str:  # pragma: no cover - trivial
        """Redacted by construction, so a stray log line cannot leak the token."""
        return f"PanelConfig(url={self.url!r}, token='<redacted>')"
