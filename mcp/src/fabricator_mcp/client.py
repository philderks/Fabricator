"""The single place an HTTP request to the panel is built.

Every tool goes through :meth:`PanelClient.request`. Nothing else assembles a
URL, sets a header, or decides what a status code means, so the retry policy and
the error taxonomy are stated once instead of fourteen times.

Query values are handed to httpx as a mapping and encoded by it. A caller value
therefore cannot smuggle in an extra parameter — the discipline that mattered
when ``?java_path=`` was an arbitrary-execution vector, and still worth keeping
now that the panel rejects it server-side.

RETRY POLICY. Retried, bounded: request timeouts and the gateway codes
502/503/504 (up to three attempts, backing off), and 429 exactly once, honouring
the panel's own ``retry_after`` up to a cap. Never retried: 401, 403, 400, 404,
500, connection refused, DNS failure, TLS failure. Those are facts about the
configuration, not weather.
"""
from __future__ import annotations

import ssl
from typing import Any, Awaitable, Callable, Mapping

import anyio
import httpx

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

#: Total attempts for one call, including the first.
MAX_ATTEMPTS = 3
#: Backoff before attempt 2 and attempt 3.
BACKOFF_SECONDS = (0.5, 1.5)
#: Transient gateway codes worth another attempt.
RETRY_STATUSES = frozenset({502, 503, 504})
#: 429 gets exactly one retry, and never sleeps longer than this.
RATE_LIMIT_RETRIES = 1
RATE_LIMIT_CAP_SECONDS = 30.0

DEFAULT_TIMEOUT_SECONDS = 30.0

_AUTH_MESSAGE = (
    "The panel rejected the API token (401). Check FABRICATOR_TOKEN is correct "
    "and has not been revoked, and that MCP access is still enabled on the "
    "panel's Integrations page. This is not retried."
)


def _clean_params(params: "Mapping[str, Any] | None") -> "dict[str, Any] | None":
    if not params:
        return None
    cleaned = {key: value for key, value in params.items() if value is not None}
    return cleaned or None


def _is_tls_failure(exc: BaseException) -> bool:
    cause: BaseException | None = exc
    while cause is not None:
        if isinstance(cause, ssl.SSLError):
            return True
        cause = cause.__cause__
    text = str(exc).lower()
    return "certificate" in text or "ssl" in text


def _body(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return None


def _error_text(response: httpx.Response) -> str:
    payload = _body(response)
    if isinstance(payload, dict):
        message = payload.get("error") or payload.get("message")
        if isinstance(message, str) and message.strip():
            return message.strip()
    return response.text.strip()[:200] or f"HTTP {response.status_code}"


def _retry_after(response: httpx.Response) -> float:
    payload = _body(response)
    if isinstance(payload, dict):
        value = payload.get("retry_after")
        if isinstance(value, (int, float)) and value >= 0:
            return min(float(value), RATE_LIMIT_CAP_SECONDS)
    header = response.headers.get("Retry-After")
    if header:
        try:
            return min(float(header), RATE_LIMIT_CAP_SECONDS)
        except ValueError:
            pass
    return 1.0


class PanelClient:
    """An async HTTP client bound to one panel and one token."""

    def __init__(
        self,
        config: PanelConfig,
        *,
        transport: "httpx.AsyncBaseTransport | None" = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        sleep: "Callable[[float], Awaitable[None]] | None" = None,
    ) -> None:
        self._config = config
        self._sleep = sleep or anyio.sleep
        self._client = httpx.AsyncClient(
            base_url=config.url,
            timeout=timeout,
            transport=transport,
            headers={
                # The only place the token is ever put on the wire.
                "Authorization": f"Bearer {config.token}",
                "Accept": "application/json",
            },
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "PanelClient":
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()

    # -- the one request path ------------------------------------------------

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: "Mapping[str, Any] | None" = None,
        json: Any = None,
    ) -> Any:
        attempt = 0
        rate_limit_retries = 0

        while True:
            attempt += 1
            try:
                response = await self._client.request(
                    method, path, params=_clean_params(params), json=json
                )
            except httpx.TimeoutException as exc:
                if attempt < MAX_ATTEMPTS:
                    await self._sleep(BACKOFF_SECONDS[attempt - 1])
                    continue
                raise PanelTimeoutError(
                    f"The panel at {self._config.url} did not respond in time "
                    f"after {attempt} attempts."
                ) from exc
            except httpx.ConnectError as exc:
                if _is_tls_failure(exc):
                    raise PanelTlsError(
                        f"TLS verification failed connecting to {self._config.url}. "
                        f"Install the panel's CA certificate, or use its http:// URL "
                        f"on a trusted local network. Verification is never disabled "
                        f"automatically."
                    ) from exc
                raise PanelUnreachableError(
                    f"Cannot reach the panel at {self._config.url}. Check the URL "
                    f"in FABRICATOR_URL, that the panel is running, and that this "
                    f"machine can reach it."
                ) from exc
            except httpx.TransportError as exc:
                raise PanelUnreachableError(
                    f"Cannot reach the panel at {self._config.url}: {type(exc).__name__}."
                ) from exc

            status = response.status_code

            if status == 401:
                raise PanelAuthError(_AUTH_MESSAGE)

            if status == 403:
                detail = _error_text(response)
                if "scope" in detail.lower():
                    raise PanelScopeError(
                        "This action needs a token with the 'manage' scope; the "
                        "token in use is read-only. Mint a manage token on the "
                        "Integrations page. This is not retried."
                    )
                raise PanelForbiddenError(
                    "The panel refuses this route for every token "
                    f"({detail}). No tool should reach this, so it points at a "
                    "version mismatch between this package and the panel, or a "
                    "permission ruling that changed. Update rather than retry."
                )

            if status == 429:
                if rate_limit_retries < RATE_LIMIT_RETRIES:
                    rate_limit_retries += 1
                    await self._sleep(_retry_after(response))
                    continue
                raise PanelRateLimitError(
                    "The panel's Modrinth request budget is exhausted "
                    f"({_error_text(response)}). Try again shortly."
                )

            if status in RETRY_STATUSES:
                if attempt < MAX_ATTEMPTS:
                    await self._sleep(BACKOFF_SECONDS[attempt - 1])
                    continue
                raise PanelUnavailableError(
                    f"The panel returned {status} after {attempt} attempts: "
                    f"{_error_text(response)}"
                )

            if status == 400:
                raise PanelRequestError(f"The panel rejected the request: {_error_text(response)}")

            if status == 404:
                raise PanelNotFoundError(
                    f"Not found: {_error_text(response)}. If this is a tool that "
                    f"should exist, the panel may be older than this package."
                )

            if status >= 500:
                raise PanelUnavailableError(
                    f"The panel returned {status}: {_error_text(response)}"
                )

            if status == 204 or not response.content:
                return None
            return _body(response)

    # -- thin helpers, all funnelling through request() -----------------------

    async def get(self, path: str, *, params: "Mapping[str, Any] | None" = None) -> Any:
        return await self.request("GET", path, params=params)

    async def post(self, path: str, *, json: Any = None) -> Any:
        return await self.request("POST", path, json=json)

    async def delete(self, path: str, *, json: Any = None) -> Any:
        return await self.request("DELETE", path, json=json)
