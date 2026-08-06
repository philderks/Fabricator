"""Tool implementations.

Each tool is a plain async function taking the :class:`PanelClient` first, so it
can be called directly in tests without standing up an MCP session. Registration
with the server is a thin wrapper in :mod:`fabricator_mcp.server`.
"""
from __future__ import annotations
