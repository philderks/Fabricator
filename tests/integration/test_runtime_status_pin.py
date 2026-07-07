"""Pin the backend's RUNTIME_KNOWN_STATUSES set as a Cross-Branch contract.

Frontend (`apps/frontend/src/utils/getEffectiveStatus.js:RUNTIME_KNOWN_STATUSES`)
mirrors this set. When the backend set changes, the frontend mirror MUST be
updated in lockstep — this test is the canary.

If you change `_RUNTIME_KNOWN_STATUSES` in `backend/server/routes.py`, you must:
1. Update this pin (see expected set below).
2. Update the frontend mirror in
   `apps/frontend/src/utils/getEffectiveStatus.js:RUNTIME_KNOWN_STATUSES`.
3. Reference the new pin from CC5 in CONVENTIONS.md.

Cross-Branch coordination: this commit (B14c on cleanup/backend) makes the
contract explicit; Frontend F6 (cleanup/frontend) consumes it via the
Status-Util migration (single source of truth in `utils/getEffectiveStatus.js`).
"""
from backend.server.routes import _RUNTIME_KNOWN_STATUSES


def test_runtime_known_statuses_is_pinned():
    """The exact runtime status set is part of the Cross-Branch contract.

    See module docstring for the lockstep update procedure.
    """
    expected = frozenset({"running", "stopped"})
    assert _RUNTIME_KNOWN_STATUSES == expected, (
        f"Backend _RUNTIME_KNOWN_STATUSES drifted: got {_RUNTIME_KNOWN_STATUSES!r}, "
        f"expected {expected!r}. Update the frontend mirror in "
        f"apps/frontend/src/utils/getEffectiveStatus.js:RUNTIME_KNOWN_STATUSES + this pin."
    )


def test_runtime_known_statuses_is_frozen():
    """Pin must be a frozenset to prevent accidental in-place mutation."""
    assert isinstance(_RUNTIME_KNOWN_STATUSES, frozenset)
