"""No tool may reach outside what a token is allowed to touch.

These assertions run everywhere, including on a machine that has only the
installed package, because they compare the tool table against the vendored
snapshot rather than against a live panel.
"""
from __future__ import annotations

from fabricator_mcp._panel_routes import (
    PANEL_MANAGE,
    PANEL_READ,
    PANEL_TOKEN_REACHABLE,
)
from fabricator_mcp.routes import MANAGE, READ, TOOL_NAMES, TOOL_ROUTES, TOOL_SCOPES


def test_every_tool_route_is_token_reachable():
    """The one that would catch a tool pointed at a NEVER route."""
    outside = sorted(
        {route for routes in TOOL_ROUTES.values() for route in routes}
        - PANEL_TOKEN_REACHABLE
    )
    assert not outside, f"tool routes the panel does not allow a token: {outside}"


def test_manage_tools_only_use_manage_or_read_routes():
    for tool, routes in TOOL_ROUTES.items():
        if TOOL_SCOPES[tool] != MANAGE:
            continue
        outside = sorted(set(routes) - PANEL_TOKEN_REACHABLE)
        assert not outside, f"{tool}: {outside}"


def test_read_tools_never_touch_a_manage_route():
    """A read-scoped tool calling a manage route would 403 at the panel; catch it here."""
    for tool, routes in TOOL_ROUTES.items():
        if TOOL_SCOPES[tool] != READ:
            continue
        escalating = sorted(set(routes) & PANEL_MANAGE)
        assert not escalating, f"read tool {tool} calls manage routes: {escalating}"


def test_manage_tools_actually_need_manage():
    """Anything declared manage should be calling at least one manage route."""
    for tool, scope in TOOL_SCOPES.items():
        if scope != MANAGE:
            continue
        assert set(TOOL_ROUTES[tool]) & PANEL_MANAGE, (
            f"{tool} is declared manage but calls no manage route"
        )


def test_read_tools_are_all_read_routes():
    for tool, scope in TOOL_SCOPES.items():
        if scope != READ:
            continue
        outside = sorted(set(TOOL_ROUTES[tool]) - PANEL_READ)
        assert not outside, f"read tool {tool} uses non-read routes: {outside}"


def test_tables_cover_the_same_tools():
    assert set(TOOL_ROUTES) == set(TOOL_SCOPES)
    assert set(TOOL_NAMES) == set(TOOL_ROUTES)
    assert len(TOOL_NAMES) == len(TOOL_ROUTES), "duplicate tool name"


def test_scopes_are_known_values():
    assert set(TOOL_SCOPES.values()) <= {READ, MANAGE}


def test_the_tool_set_is_narrower_than_the_ceiling():
    """Curation, stated as a fact: tools use a strict subset of the permitted routes."""
    used = {route for routes in TOOL_ROUTES.values() for route in routes}
    assert used < PANEL_TOKEN_REACHABLE
    assert len(TOOL_ROUTES) == 14
