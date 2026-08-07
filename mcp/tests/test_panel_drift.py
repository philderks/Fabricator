"""The vendored panel table must still match the panel.

WHY THIS LOADS A FILE INSTEAD OF IMPORTING IT
---------------------------------------------
``import backend.auth.buckets`` executes ``backend/auth/__init__.py`` on the way
in, and that module is the request gate: it imports Flask. This island has no
Flask by design, so the import raises, the test skips, and a CI that demands the
check would be permanently red for the wrong reason.

``buckets.py`` itself imports nothing but ``__future__`` — verified before this
was written — so loading the file directly by path is Flask-free and gives the
real table.

SKIP VERSUS FAIL
----------------
* Panel source **absent** -> skip. Legitimate: someone running this suite from
  an installed sdist has no ``backend/`` and never will.
* Panel source **present but unreadable, unparseable, or missing BUCKETS** ->
  fail. That is drift, corruption, or a rename, and silence would be the whole
  problem this test exists to prevent.
* ``FABRICATOR_MCP_REQUIRE_PANEL=1`` -> absent becomes a failure too. CI sets
  it, so the check can never quietly stop running there.
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest

from fabricator_mcp._panel_routes import (
    PANEL_MANAGE,
    PANEL_READ,
    PANEL_TABLE_REVISION,
)

REQUIRE_PANEL_ENV = "FABRICATOR_MCP_REQUIRE_PANEL"

#: mcp/tests/test_panel_drift.py -> mcp/tests -> mcp -> <repo root>
_REPO_ROOT = Path(__file__).resolve().parents[2]
_PANEL_BUCKETS = _REPO_ROOT / "backend" / "auth" / "buckets.py"


def load_panel_buckets(path: Path | None = None):
    """Return the panel's live BUCKETS, or None when the source is absent.

    Raises rather than returning None when the file is there but unusable.
    """
    target = _PANEL_BUCKETS if path is None else path
    if not target.exists():
        return None

    spec = importlib.util.spec_from_file_location("_fabricator_panel_buckets", target)
    if spec is None or spec.loader is None:
        raise AssertionError(f"panel table present but not loadable: {target}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # a syntax error here SHOULD fail the test

    try:
        return module.BUCKETS
    except AttributeError as exc:
        raise AssertionError(f"{target} no longer defines BUCKETS") from exc


def _live_or_skip():
    buckets = load_panel_buckets()
    if buckets is not None:
        return buckets
    if os.environ.get(REQUIRE_PANEL_ENV):
        pytest.fail(
            f"{REQUIRE_PANEL_ENV} is set but the panel source is not at "
            f"{_PANEL_BUCKETS}. The drift check cannot be skipped in CI."
        )
    pytest.skip(
        "panel source not present (installed package); CI sets "
        f"{REQUIRE_PANEL_ENV}=1 so this cannot silently stop running there"
    )


def test_vendored_read_set_matches_the_panel():
    buckets = _live_or_skip()
    live = {key for key, bucket in buckets.items() if bucket == "read"}
    assert PANEL_READ == live, (
        "the panel's read set moved under the vendored snapshot "
        f"(revision {PANEL_TABLE_REVISION}); re-audit the difference, do not just re-copy it"
    )


def test_vendored_manage_set_matches_the_panel():
    buckets = _live_or_skip()
    live = {key for key, bucket in buckets.items() if bucket == "manage"}
    assert PANEL_MANAGE == live, (
        "the panel's manage set moved under the vendored snapshot "
        f"(revision {PANEL_TABLE_REVISION}); re-audit the difference, do not just re-copy it"
    )


def test_no_vendored_route_is_never_on_the_panel():
    """The direction that matters most: nothing we call may have become NEVER."""
    buckets = _live_or_skip()
    now_never = sorted(
        route for route in (PANEL_READ | PANEL_MANAGE)
        if buckets.get(route) == "never"
    )
    assert not now_never, f"routes the panel has since forbidden to every token: {now_never}"


# --- the skip/fail distinction itself ---------------------------------------

def test_absent_panel_source_returns_none(tmp_path):
    assert load_panel_buckets(tmp_path / "does-not-exist.py") is None


def test_unparseable_panel_table_fails_rather_than_skipping(tmp_path):
    broken = tmp_path / "buckets.py"
    broken.write_text("this is not = valid python =\n", encoding="utf-8")
    with pytest.raises(SyntaxError):
        load_panel_buckets(broken)


def test_panel_table_without_BUCKETS_fails(tmp_path):
    renamed = tmp_path / "buckets.py"
    renamed.write_text("SOMETHING_ELSE = {}\n", encoding="utf-8")
    with pytest.raises(AssertionError, match="BUCKETS"):
        load_panel_buckets(renamed)


def test_loading_the_panel_table_needs_no_flask():
    """The whole reason for the file-path load: this island has no Flask."""
    assert importlib.util.find_spec("flask") is None
    assert load_panel_buckets() is not None, "panel source expected in a repo checkout"
