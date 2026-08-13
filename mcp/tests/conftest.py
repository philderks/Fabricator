"""Shared fixtures for the island's suite.

NO TEST IN THIS PACKAGE EVER REACHES THE NETWORK. That is enforced here, not
asked for politely: a Unit A test once reached the live internet through a warm
``lru_cache`` and passed in isolation while failing only in the full suite. The
autouse guard below makes an un-mocked request fail the test loudly instead of
escaping.

Tests that need a panel build an ``httpx.MockTransport`` explicitly; that class
is not patched, so mocked traffic works normally while real traffic cannot.
"""
from __future__ import annotations

import pytest


class NetworkAccessAttempted(AssertionError):
    """Raised when a test tries to open a real connection."""


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """Block httpx's real transports for every test in this package."""
    import httpx

    def _blocked(self, request, *args, **kwargs):
        raise NetworkAccessAttempted(
            f"un-mocked network call to {request.url!r}. Tests must drive the "
            f"client with httpx.MockTransport; no test may reach a live panel."
        )

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", _blocked, raising=True)
    monkeypatch.setattr(
        httpx.AsyncHTTPTransport, "handle_async_request", _blocked, raising=True
    )


@pytest.fixture
def anyio_backend():
    """Run ``@pytest.mark.anyio`` tests on asyncio only (no trio in the closure)."""
    return "asyncio"


@pytest.fixture
def env(monkeypatch):
    """A clean environment with the two settings the package reads."""
    monkeypatch.delenv("FABRICATOR_URL", raising=False)
    monkeypatch.delenv("FABRICATOR_TOKEN", raising=False)
    return monkeypatch
