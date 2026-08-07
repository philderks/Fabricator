"""The error taxonomy.

Every failure a tool can hit resolves to one of these, and each carries a
message written for the person who has to fix it rather than for a stack trace.
Two rules hold throughout:

* **A configuration fact is never retried.** 401 and 403 are deterministic —
  the same token against the same route gives the same answer forever — so
  retrying only hides a fixable cause behind repeated failure.
* **A message never contains the token.** Not in the text, not in a repr, not
  in a wrapped cause.
"""
from __future__ import annotations


class PanelError(RuntimeError):
    """Base class for every failure talking to the panel."""


# --- authentication / authorisation: never retried --------------------------

class PanelAuthError(PanelError):
    """401. Bad, revoked or expired token, or MCP access is switched off.

    The status code cannot separate those causes, so the message names both
    rather than guessing.
    """


class PanelScopeError(PanelError):
    """403 for scope: a manage-only route reached with a read token."""


class PanelForbiddenError(PanelError):
    """403 for the route itself: forbidden to every token, whatever its scope.

    A tool should never produce this, because no tool maps to such a route. If
    it happens, the package and the panel disagree about the permission table —
    version skew, or a ruling that changed under us.
    """


# --- request / route problems: never retried --------------------------------

class PanelRequestError(PanelError):
    """400. The panel rejected the request itself; its message is carried through."""


class PanelNotFoundError(PanelError):
    """404. The route or the thing it addresses is not there."""


# --- transport and availability ---------------------------------------------

class PanelUnreachableError(PanelError):
    """Connection refused, DNS failure, no route. A configuration fact: no retry."""


class PanelTlsError(PanelError):
    """Certificate verification failed. Never worked around by disabling checks."""


class PanelTimeoutError(PanelError):
    """The panel did not answer in time, after the bounded retries."""


class PanelUnavailableError(PanelError):
    """5xx from the panel. Gateway codes are retried briefly; 500 is not."""


class PanelRateLimitError(PanelError):
    """429 — the panel's Modrinth budget is spent, and the one retry did not help."""
