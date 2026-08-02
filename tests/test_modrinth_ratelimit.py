"""Tests for backend.modrinth.ratelimit — the token bucket and its corrections.

Covers issue #52: the client had no throttle at all, so a fan-out on the mods
page could spend Modrinth's whole 300/min per-IP budget in seconds.

Time is driven through a fake monotonic clock rather than real sleeps — a test
that waits out a 60s refill window would be useless in CI.
"""
from __future__ import annotations

import importlib
import threading

import pytest

from backend.modrinth.ratelimit import RateLimiter, RateLimitExceeded


@pytest.fixture(autouse=True)
def _fresh_modules():
    """Re-bind against what sys.modules holds NOW — test_app_factory.py purges
    every `backend.*` module, and a stale RateLimiter class here would be
    patched in one module while the code under test used another. Same idiom as
    test_playit_provision.py."""
    global RateLimiter, RateLimitExceeded
    module = importlib.import_module("backend.modrinth.ratelimit")
    RateLimiter = module.RateLimiter
    RateLimitExceeded = module.RateLimitExceeded


@pytest.fixture
def clock(monkeypatch):
    """A controllable monotonic clock shared by the limiter under test."""
    class Clock:
        def __init__(self):
            self.now = 1000.0

        def __call__(self):
            return self.now

        def advance(self, seconds):
            self.now += seconds

    fake = Clock()
    monkeypatch.setattr("backend.modrinth.ratelimit.time.monotonic", fake)
    return fake


def _limiter(**kwargs):
    defaults = dict(capacity=10, window_seconds=10.0, max_wait=0.0)
    defaults.update(kwargs)
    return RateLimiter(**defaults)


# ---------------------------------------------------------------------------
# Token bucket
# ---------------------------------------------------------------------------

def test_capacity_is_spendable_then_exhausted(clock):
    """max_wait=0 turns "would have to wait" into an immediate signal, which is
    what lets us assert the budget without sleeping."""
    limiter = _limiter()
    for _ in range(10):
        limiter.acquire()

    with pytest.raises(RateLimitExceeded):
        limiter.acquire()


def test_tokens_refill_over_time(clock):
    limiter = _limiter()
    for _ in range(10):
        limiter.acquire()

    clock.advance(3.0)          # 10 tokens / 10s => 3 tokens back
    for _ in range(3):
        limiter.acquire()
    with pytest.raises(RateLimitExceeded):
        limiter.acquire()


def test_refill_never_exceeds_capacity(clock):
    """An idle limiter must not bank an unbounded burst."""
    limiter = _limiter()
    clock.advance(10_000)
    for _ in range(10):
        limiter.acquire()
    with pytest.raises(RateLimitExceeded):
        limiter.acquire()


def test_retry_after_reports_the_wait(clock):
    limiter = _limiter()
    for _ in range(10):
        limiter.acquire()

    with pytest.raises(RateLimitExceeded) as excinfo:
        limiter.acquire()
    # 1 token at 1/sec => ~1s.
    assert 0 < excinfo.value.retry_after <= 1.0


def test_acquire_waits_when_allowed_to(clock):
    """With headroom in max_wait the call blocks and then succeeds, instead of
    failing a request that only needed to wait a moment."""
    limiter = _limiter(max_wait=5.0)
    for _ in range(10):
        limiter.acquire()

    done = threading.Event()

    def _worker():
        limiter.acquire()
        done.set()

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    # The waiter is parked on a condition with a timeout computed from the fake
    # clock; advancing it and notifying lets it re-check and find a token.
    clock.advance(2.0)
    with limiter._cond:
        limiter._cond.notify_all()

    assert done.wait(timeout=5), "waiter should have acquired after the refill"


# ---------------------------------------------------------------------------
# Server-driven corrections
# ---------------------------------------------------------------------------

def test_observe_clamps_to_the_reported_remaining(clock):
    """The budget is per-IP and shared with other clients, so the API's count
    is authoritative when it is lower than ours."""
    limiter = _limiter()
    limiter.observe({"X-Ratelimit-Remaining": "2"})

    limiter.acquire()
    limiter.acquire()
    with pytest.raises(RateLimitExceeded):
        limiter.acquire()


def test_observe_never_raises_the_local_budget(clock):
    """A generous remaining count must not let us exceed our own capacity."""
    limiter = _limiter()
    for _ in range(10):
        limiter.acquire()
    limiter.observe({"X-Ratelimit-Remaining": "300"})

    with pytest.raises(RateLimitExceeded):
        limiter.acquire()


def test_observe_zero_remaining_parks_until_reset(clock):
    limiter = _limiter(max_wait=0.0)
    limiter.observe({"X-Ratelimit-Remaining": "0", "X-Ratelimit-Reset": "30"})

    with pytest.raises(RateLimitExceeded) as excinfo:
        limiter.acquire()
    assert excinfo.value.retry_after == pytest.approx(30.0, abs=0.5)

    clock.advance(31)
    limiter.acquire()


def test_observe_ignores_missing_or_junk_headers(clock):
    limiter = _limiter()
    limiter.observe(None)
    limiter.observe({})
    limiter.observe({"X-Ratelimit-Remaining": "not-a-number"})
    limiter.acquire()  # unaffected


def test_penalize_parks_every_caller(clock):
    limiter = _limiter()
    cooldown = limiter.penalize(45)
    assert cooldown == 45

    with pytest.raises(RateLimitExceeded) as excinfo:
        limiter.acquire()
    assert excinfo.value.retry_after == pytest.approx(45.0, abs=0.5)

    clock.advance(46)
    limiter.acquire()


def test_penalize_without_retry_after_uses_a_default(clock):
    limiter = _limiter()
    assert limiter.penalize(None) > 0
    with pytest.raises(RateLimitExceeded):
        limiter.acquire()


def test_penalize_extends_but_never_shortens_a_cooldown(clock):
    """A second 429 arriving mid-cooldown must not let callers out early."""
    limiter = _limiter()
    limiter.penalize(60)
    limiter.penalize(5)

    clock.advance(10)
    with pytest.raises(RateLimitExceeded):
        limiter.acquire()


def test_reset_refills_and_clears_cooldown(clock):
    limiter = _limiter()
    limiter.penalize(120)
    limiter.reset()
    for _ in range(10):
        limiter.acquire()


def test_shared_limiter_is_the_default_for_every_client():
    """The budget is per-IP: two clients that each had their own bucket would
    together spend twice the limit."""
    from backend.modrinth.client import ModrinthClient
    from backend.modrinth.ratelimit import shared_limiter

    assert ModrinthClient().limiter is shared_limiter
    assert ModrinthClient().limiter is ModrinthClient().limiter


def test_concurrent_acquire_never_oversubscribes(clock):
    """The bucket is shared across request threads; spending must be atomic."""
    limiter = _limiter(capacity=50, window_seconds=10_000.0, max_wait=0.0)
    granted = []
    lock = threading.Lock()

    def _worker():
        try:
            limiter.acquire()
        except RateLimitExceeded:
            return
        with lock:
            granted.append(1)

    threads = [threading.Thread(target=_worker) for _ in range(120)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert len(granted) == 50, "exactly the capacity may be handed out"


# ---------------------------------------------------------------------------
# Integration with ModrinthClient._request
# ---------------------------------------------------------------------------

def _client(limiter):
    from unittest.mock import MagicMock
    from backend.modrinth.client import ModrinthClient

    client = ModrinthClient(limiter=limiter)
    client.session = MagicMock()
    return client


def _response(status=200, headers=None, payload=None):
    from unittest.mock import MagicMock
    import requests

    response = MagicMock()
    response.status_code = status
    response.headers = headers or {}
    response.json.return_value = payload if payload is not None else {}
    if status >= 400:
        error = requests.exceptions.HTTPError(response=response)
        response.raise_for_status.side_effect = error
    else:
        response.raise_for_status.return_value = None
    return response


def test_request_spends_a_token_before_going_out():
    from backend.modrinth.client import ModrinthApiError

    limiter = RateLimiter(capacity=1, window_seconds=1000.0, max_wait=0.0)
    client = _client(limiter)
    client.session.request.return_value = _response()

    client._request("get", "https://example/1", error_context="ctx")

    with pytest.raises(ModrinthApiError) as excinfo:
        client._request("get", "https://example/2", error_context="ctx")

    assert excinfo.value.status_code == 429
    assert excinfo.value.details["retry_after"] > 0
    # The blocked call must never reach the network — that is the whole point.
    assert client.session.request.call_count == 1


def test_successful_response_reconciles_the_budget():
    from backend.modrinth.client import ModrinthApiError

    limiter = RateLimiter(capacity=100, window_seconds=10_000.0, max_wait=0.0)
    client = _client(limiter)
    client.session.request.return_value = _response(headers={"X-Ratelimit-Remaining": "1"})

    client._request("get", "https://example/1", error_context="ctx")
    client._request("get", "https://example/2", error_context="ctx")

    # Modrinth said 1 remaining, so the local bucket is down to that regardless
    # of our own generous capacity.
    with pytest.raises(ModrinthApiError):
        client._request("get", "https://example/3", error_context="ctx")


def test_429_from_the_api_pauses_the_limiter_and_reports_retry_after():
    from backend.modrinth.client import ModrinthApiError

    limiter = RateLimiter(capacity=100, window_seconds=10_000.0, max_wait=0.0)
    client = _client(limiter)
    client.session.request.return_value = _response(
        status=429, headers={"Retry-After": "42"}
    )

    with pytest.raises(ModrinthApiError) as excinfo:
        client._request("get", "https://example/1", error_context="ctx")

    assert excinfo.value.status_code == 429
    assert excinfo.value.details["retry_after"] == pytest.approx(42.0, abs=1.0)
    assert limiter.retry_after() == pytest.approx(42.0, abs=1.0)

    # Every later caller is parked, not just the one that got the 429.
    with pytest.raises(ModrinthApiError) as later:
        client._request("get", "https://example/2", error_context="ctx")
    assert later.value.status_code == 429


def test_429_without_retry_after_still_pauses():
    from backend.modrinth.client import ModrinthApiError

    limiter = RateLimiter(capacity=100, window_seconds=10_000.0, max_wait=0.0)
    client = _client(limiter)
    client.session.request.return_value = _response(status=429)

    with pytest.raises(ModrinthApiError):
        client._request("get", "https://example/1", error_context="ctx")
    assert limiter.retry_after() > 0


def test_non_429_errors_do_not_pause_the_limiter():
    """A 404 is a normal answer, not a budget signal — pausing on it would
    stall the panel for every missing project."""
    from backend.modrinth.client import ModrinthApiError

    limiter = RateLimiter(capacity=100, window_seconds=10_000.0, max_wait=0.0)
    client = _client(limiter)
    client.session.request.return_value = _response(status=404)

    with pytest.raises(ModrinthApiError) as excinfo:
        client._request("get", "https://example/1", error_context="Failed to fetch project")

    assert excinfo.value.status_code == 404
    assert "retry_after" not in excinfo.value.details
    assert limiter.retry_after() == 0
