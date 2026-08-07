"""Every error surface, and the retry policy, asserted by counting requests.

A "no retry" claim is only worth anything if something counts the attempts, so
each case below asserts the number of times the transport was called, not just
the exception type.
"""
from __future__ import annotations

import ssl

import httpx
import pytest

from fabricator_mcp.client import MAX_ATTEMPTS, PanelClient
from fabricator_mcp.config import PanelConfig
from fabricator_mcp.errors import (
    PanelAuthError,
    PanelForbiddenError,
    PanelNotFoundError,
    PanelRateLimitError,
    PanelRequestError,
    PanelScopeError,
    PanelTimeoutError,
    PanelTlsError,
    PanelUnavailableError,
    PanelUnreachableError,
)

pytestmark = pytest.mark.anyio

_TOKEN = "fab_abc123_supersecretvalue"
_CONFIG = PanelConfig(url="http://panel.test:5000", token=_TOKEN)


class Recorder:
    """A MockTransport that records every request it is handed."""

    def __init__(self, responder):
        self.requests: list[httpx.Request] = []
        self._responder = responder
        self.transport = httpx.MockTransport(self._handle)

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        result = self._responder(request, len(self.requests))
        if isinstance(result, Exception):
            raise result
        return result

    @property
    def calls(self) -> int:
        return len(self.requests)


def client_for(recorder, **kwargs) -> PanelClient:
    async def _no_sleep(_seconds: float) -> None:
        return None

    return PanelClient(_CONFIG, transport=recorder.transport, sleep=_no_sleep, **kwargs)


def status(code: int, payload=None):
    def _responder(_request, _attempt):
        return httpx.Response(code, json=payload if payload is not None else {})

    return Recorder(_responder)


# --- authentication and authorisation: never retried ------------------------

async def test_401_raises_auth_error_and_is_not_retried():
    recorder = status(401, {"error": "invalid token"})
    async with client_for(recorder) as client:
        with pytest.raises(PanelAuthError) as exc:
            await client.get("/api/servers")
    assert recorder.calls == 1
    assert "not retried" in str(exc.value).lower()


async def test_401_from_the_switch_being_off_says_so_too():
    recorder = status(401, {"error": "mcp token auth disabled"})
    async with client_for(recorder) as client:
        with pytest.raises(PanelAuthError) as exc:
            await client.get("/api/servers")
    # One code, two causes: the message must name both rather than guess.
    message = str(exc.value)
    assert "FABRICATOR_TOKEN" in message
    assert "Integrations" in message
    assert recorder.calls == 1


async def test_403_insufficient_scope_is_a_scope_error_and_not_retried():
    recorder = status(403, {"error": "insufficient scope"})
    async with client_for(recorder) as client:
        with pytest.raises(PanelScopeError) as exc:
            await client.post("/api/servers/s1/start")
    assert recorder.calls == 1
    assert "manage" in str(exc.value)


async def test_403_forbidden_route_is_distinct_and_not_retried():
    recorder = status(403, {"error": "forbidden for token"})
    async with client_for(recorder) as client:
        with pytest.raises(PanelForbiddenError) as exc:
            await client.get("/api/servers/s1/files")
    assert recorder.calls == 1
    assert "version mismatch" in str(exc.value)


# --- request problems: never retried ----------------------------------------

async def test_400_carries_the_panel_message_and_is_not_retried():
    recorder = status(400, {"error": "java_path is not accepted for token-authenticated requests"})
    async with client_for(recorder) as client:
        with pytest.raises(PanelRequestError) as exc:
            await client.get("/api/java/status")
    assert recorder.calls == 1
    assert "java_path" in str(exc.value)


async def test_404_is_not_retried_and_hints_at_panel_age():
    recorder = status(404, {"error": "Server not found"})
    async with client_for(recorder) as client:
        with pytest.raises(PanelNotFoundError) as exc:
            await client.get("/api/servers/nope")
    assert recorder.calls == 1
    assert "older" in str(exc.value)


async def test_500_is_not_retried():
    recorder = status(500, {"error": "boom"})
    async with client_for(recorder) as client:
        with pytest.raises(PanelUnavailableError):
            await client.get("/api/servers")
    assert recorder.calls == 1


# --- bounded retries --------------------------------------------------------

@pytest.mark.parametrize("code", [502, 503, 504])
async def test_gateway_codes_retry_up_to_the_bound(code):
    recorder = status(code)
    async with client_for(recorder) as client:
        with pytest.raises(PanelUnavailableError):
            await client.get("/api/servers")
    assert recorder.calls == MAX_ATTEMPTS == 3


async def test_gateway_code_that_recovers_returns_the_body():
    def _responder(_request, attempt):
        if attempt == 1:
            return httpx.Response(503, json={})
        return httpx.Response(200, json={"ok": True})

    recorder = Recorder(_responder)
    async with client_for(recorder) as client:
        assert await client.get("/api/servers") == {"ok": True}
    assert recorder.calls == 2


async def test_timeout_retries_then_surfaces():
    def _responder(request, _attempt):
        return httpx.ReadTimeout("too slow", request=request)

    recorder = Recorder(_responder)
    async with client_for(recorder) as client:
        with pytest.raises(PanelTimeoutError):
            await client.get("/api/servers")
    assert recorder.calls == MAX_ATTEMPTS


async def test_rate_limit_retries_exactly_once():
    recorder = status(429, {"error": "rate limited", "retry_after": 0.01})
    async with client_for(recorder) as client:
        with pytest.raises(PanelRateLimitError):
            await client.get("/api/modrinth/search")
    assert recorder.calls == 2  # the first, plus exactly one retry


async def test_rate_limit_that_clears_returns_the_body():
    def _responder(_request, attempt):
        if attempt == 1:
            return httpx.Response(429, json={"retry_after": 0.01})
        return httpx.Response(200, json=[{"projectId": "sodium"}])

    recorder = Recorder(_responder)
    async with client_for(recorder) as client:
        assert await client.get("/api/modrinth/search") == [{"projectId": "sodium"}]
    assert recorder.calls == 2


# --- transport --------------------------------------------------------------

async def test_connection_refused_is_unreachable_and_not_retried():
    def _responder(request, _attempt):
        return httpx.ConnectError("connection refused", request=request)

    recorder = Recorder(_responder)
    async with client_for(recorder) as client:
        with pytest.raises(PanelUnreachableError) as exc:
            await client.get("/api/health")
    assert recorder.calls == 1
    assert "FABRICATOR_URL" in str(exc.value)


async def test_tls_failure_is_its_own_error_and_never_disables_verification():
    def _responder(request, _attempt):
        error = httpx.ConnectError("certificate verify failed", request=request)
        error.__cause__ = ssl.SSLCertVerificationError("self signed certificate")
        return error

    recorder = Recorder(_responder)
    async with client_for(recorder) as client:
        with pytest.raises(PanelTlsError) as exc:
            await client.get("/api/health")
    assert recorder.calls == 1
    assert "never disabled" in str(exc.value)


# --- request construction ---------------------------------------------------

async def test_the_token_rides_in_the_header_and_never_in_the_url():
    recorder = status(200, {"ok": True})
    async with client_for(recorder) as client:
        await client.get("/api/servers", params={"limit": 5})
    request = recorder.requests[0]
    assert request.headers["Authorization"] == f"Bearer {_TOKEN}"
    assert _TOKEN not in str(request.url)


async def test_none_params_are_dropped_rather_than_sent_as_empty():
    recorder = status(200, {})
    async with client_for(recorder) as client:
        await client.get("/api/modrinth/search", params={"query": "sodium", "loader": None})
    assert recorder.requests[0].url.params.get("query") == "sodium"
    assert "loader" not in recorder.requests[0].url.params


async def test_params_are_encoded_so_a_value_cannot_add_a_parameter():
    """A crafted value must stay one value, not become a second parameter."""
    recorder = status(200, {})
    async with client_for(recorder) as client:
        await client.get("/api/java/status", params={"mc_version": "1.20&java_path=cmd.exe"})
    url = recorder.requests[0].url
    assert url.params.get("mc_version") == "1.20&java_path=cmd.exe"
    assert "java_path" not in url.params


async def test_204_returns_none():
    def _responder(_request, _attempt):
        return httpx.Response(204)

    recorder = Recorder(_responder)
    async with client_for(recorder) as client:
        assert await client.delete("/api/servers/s1/mods") is None


async def test_no_error_message_ever_contains_the_token():
    cases = [
        (401, {"error": "invalid token"}),
        (403, {"error": "insufficient scope"}),
        (403, {"error": "forbidden for token"}),
        (400, {"error": "bad"}),
        (404, {"error": "nope"}),
        (500, {"error": "boom"}),
    ]
    for code, payload in cases:
        recorder = status(code, payload)
        async with client_for(recorder) as client:
            with pytest.raises(Exception) as exc:
                await client.get("/api/servers")
        assert _TOKEN not in str(exc.value)
        assert _TOKEN not in repr(exc.value)
