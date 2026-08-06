"""MCP server construction.

Transport is local stdio: this process runs on the user's own machine, next to
their MCP client, and reaches the panel over HTTP with a bearer token. There is
no hosted variant — a remote connector would be dialled from the vendor's cloud
and could never reach a LAN-only self-hosted panel.

Tools are registered on top of this in later commits; the surface here is the
server object and how it is run.
"""
from __future__ import annotations

from fabricator_mcp.config import PanelConfig

SERVER_NAME = "fabricator"


def build_server(config: PanelConfig):
    """Return the MCP server for ``config``, with its tools registered."""
    from mcp.server.fastmcp import FastMCP

    server = FastMCP(SERVER_NAME)
    # Tools land here in the read/manage commits.
    return server


def run(config: PanelConfig) -> None:  # pragma: no cover - blocks on stdio
    """Serve over stdio until the client closes the transport."""
    build_server(config).run()
