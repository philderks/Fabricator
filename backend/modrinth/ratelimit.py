"""Client-side rate limiting for the Modrinth API.

Modrinth allows 300 requests/minute per IP and reports the live budget on every
response via ``X-Ratelimit-Limit`` / ``-Remaining`` / ``-Reset``. Fabricator had
no throttle at all: every panel request mapped 1:1 onto an API request, so a
mods page that fanned out could blow the budget in seconds and get the whole
deployment 429'd — including any other Modrinth client on the same IP (issue
#52).

This is a token bucket shared by every ModrinthClient in the process, plus two
server-driven corrections:

* ``observe()`` clamps the local bucket to the ``X-Ratelimit-Remaining`` the API
  just reported, so we converge on the server's view rather than our own guess.
  That matters because the budget is per-IP: another Fabricator instance, or the
  user's Modrinth desktop app, spends from the same pool.
* ``penalize()`` parks every caller until ``Retry-After`` elapses once a 429 is
  actually returned.

Requests block while waiting for a token, but only up to ``max_wait`` — past
that the caller gets :class:`RateLimitExceeded` and the route turns it into a
429 with a ``retry_after``, which is far kinder than a request that hangs.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Mapping, Optional

logger = logging.getLogger(__name__)

# Modrinth's documented ceiling is 300/min. We spend at 250 to leave headroom
# for the other clients sharing this IP and for the window-edge imprecision of
# a local bucket vs. the server's fixed window.
DEFAULT_CAPACITY = 250
DEFAULT_WINDOW_SECONDS = 60.0

# How long a request may block waiting for a token before it gives up. Long
# enough to absorb a burst, short enough that a page load fails visibly instead
# of appearing to hang.
DEFAULT_MAX_WAIT_SECONDS = 10.0

# Fallback when a 429 arrives with no usable Retry-After header.
_DEFAULT_PENALTY_SECONDS = 10.0


class RateLimitExceeded(Exception):
    """No token became available within ``max_wait``.

    ``retry_after`` is in seconds and is meant to be handed straight to the
    caller — the frontend's backoff helper already reads it.
    """

    def __init__(self, retry_after: float):
        self.retry_after = max(0.0, float(retry_after))
        super().__init__(
            f"Modrinth rate limit reached; retry in {self.retry_after:.0f}s"
        )


class RateLimiter:
    """Thread-safe token bucket with a server-driven cooldown."""

    def __init__(
        self,
        capacity: int = DEFAULT_CAPACITY,
        window_seconds: float = DEFAULT_WINDOW_SECONDS,
        max_wait: float = DEFAULT_MAX_WAIT_SECONDS,
    ):
        self._capacity = float(max(1, capacity))
        self._refill_per_sec = self._capacity / float(window_seconds)
        self._max_wait = float(max_wait)

        self._tokens = self._capacity
        self._updated = time.monotonic()
        self._cooldown_until = 0.0
        # Condition, not Lock: penalize()/observe() must be able to wake waiters
        # early when the picture changes rather than let them sleep out a stale
        # timeout.
        self._cond = threading.Condition()

    # -- internal ---------------------------------------------------------

    def _refill_locked(self, now: float) -> None:
        elapsed = now - self._updated
        if elapsed > 0:
            self._tokens = min(self._capacity, self._tokens + elapsed * self._refill_per_sec)
            self._updated = now

    # -- public -----------------------------------------------------------

    def acquire(self) -> None:
        """Spend one token, blocking until one is available.

        Raises RateLimitExceeded when that would take longer than ``max_wait``.
        """
        deadline = time.monotonic() + self._max_wait

        with self._cond:
            while True:
                now = time.monotonic()
                self._refill_locked(now)

                if now < self._cooldown_until:
                    wait = self._cooldown_until - now
                elif self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return
                else:
                    wait = (1.0 - self._tokens) / self._refill_per_sec

                if now + wait > deadline:
                    raise RateLimitExceeded(retry_after=wait)

                # Re-checked on wake: another thread may have spent the token we
                # were waiting for, or penalize() may have extended the cooldown.
                self._cond.wait(timeout=wait)

    def observe(self, headers: Optional[Mapping[str, str]]) -> None:
        """Reconcile the bucket with the budget the API just reported.

        Only ever lowers the local token count — the API's remaining count is
        authoritative about the shared per-IP pool, but a high value must not
        let us hand out more than our own capacity allows.
        """
        if not headers:
            return
        remaining = _read_int(headers, "X-Ratelimit-Remaining")
        if remaining is None:
            return

        with self._cond:
            self._refill_locked(time.monotonic())
            if remaining < self._tokens:
                self._tokens = float(remaining)
            if remaining <= 0:
                reset = _read_int(headers, "X-Ratelimit-Reset")
                self._cooldown_locked(float(reset) if reset is not None
                                      else _DEFAULT_PENALTY_SECONDS)

    def penalize(self, retry_after: Optional[float] = None) -> float:
        """Park all callers after a 429. Returns the cooldown in seconds."""
        seconds = retry_after if retry_after and retry_after > 0 else _DEFAULT_PENALTY_SECONDS
        with self._cond:
            self._tokens = 0.0
            self._cooldown_locked(seconds)
            logger.warning("modrinth: rate limited by the API; pausing %.0fs", seconds)
            return seconds

    def _cooldown_locked(self, seconds: float) -> None:
        self._cooldown_until = max(self._cooldown_until, time.monotonic() + seconds)
        self._cond.notify_all()

    def retry_after(self) -> float:
        """Seconds until the current cooldown lifts (0 when not cooling down)."""
        with self._cond:
            return max(0.0, self._cooldown_until - time.monotonic())

    def reset(self) -> None:
        """Refill the bucket and clear any cooldown.

        For tests: the limiter is process-wide by design, so without a reset
        between cases the tokens spent by one test (and any cooldown it
        deliberately triggered) would leak into the next and eventually make
        an unrelated test block or 429.
        """
        with self._cond:
            self._tokens = self._capacity
            self._updated = time.monotonic()
            self._cooldown_until = 0.0
            self._cond.notify_all()


def _read_int(headers: Mapping[str, str], name: str) -> Optional[int]:
    raw = headers.get(name)
    if raw is None:
        return None
    try:
        return int(str(raw).strip())
    except (TypeError, ValueError):
        return None


# Process-wide: the budget is per-IP, so every ModrinthClient instance (routes,
# installers, tests) must spend from the same bucket for the limit to mean
# anything.
shared_limiter = RateLimiter()
