"""Fabricator MCP server — runs on the user's machine, talks to their panel.

The import package is deliberately ``fabricator_mcp`` and never ``mcp``: the
Model Context Protocol SDK owns that name, and a local package called ``mcp``
would shadow it for this process and everything in it.
"""
from __future__ import annotations

__all__ = ["__version__"]

__version__ = "0.2.0"
