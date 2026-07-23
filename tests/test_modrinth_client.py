"""Pin ModrinthClient class-level path-set invariants.

The two path-sets ``MODPACK_SWITCH_PATHS`` (sub-paths replaced by an
incoming modpack) and ``PROTECTED_SERVER_PATHS`` (never touched by a
switch) must be disjoint — otherwise a modpack-switch would silently
overwrite a protected directory like ``world`` or ``backups``.

In addition, ``clean_modpack_switch_paths`` enforces a runtime guard
that skips ``PROTECTED_SERVER_PATHS`` entries even if a future caller
passes a widened path-set. Under shipped callers the guard is
unreachable (because of the disjointness above), but the contract is
exercised directly here via monkeypatch.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from backend.modrinth.client import ModrinthApiError, ModrinthClient


def test_modpack_switch_paths_and_protected_paths_are_disjoint():
    switchable = set(ModrinthClient.MODPACK_SWITCH_PATHS)
    protected = set(ModrinthClient.PROTECTED_SERVER_PATHS)
    overlap = switchable & protected
    assert not overlap, (
        f"MODPACK_SWITCH_PATHS overlaps PROTECTED_SERVER_PATHS: {overlap}. "
        "A modpack switch would silently overwrite a protected server path."
    )


def test_clean_modpack_switch_paths_guard_skips_protected_paths(tmp_path, monkeypatch):
    """The runtime guard skips PROTECTED_SERVER_PATHS entries even if
    MODPACK_SWITCH_PATHS is artificially widened to include them.

    Under shipped callers the two sets are disjoint (pinned by the test
    above), so this branch is unreachable from production code. The
    monkeypatch exercises the method-boundary contract directly — the
    guard is real, not theater.
    """
    (tmp_path / "mods").mkdir()
    (tmp_path / "mods" / "test.jar").write_text("x")
    (tmp_path / "world").mkdir()
    (tmp_path / "world" / "level.dat").write_text("savedata")

    client = ModrinthClient()
    monkeypatch.setattr(client, "MODPACK_SWITCH_PATHS", ("mods", "world"))

    removed = client.clean_modpack_switch_paths(tmp_path)

    assert "mods" in removed
    assert "world" not in removed
    assert not (tmp_path / "mods").exists()
    assert (tmp_path / "world" / "level.dat").read_text() == "savedata"


def _fake_response(*, status=200, json_value=None, json_raises=False, text=""):
    """A MagicMock standing in for a requests.Response the session returns."""
    resp = MagicMock()
    resp.status_code = status
    resp.raise_for_status.return_value = None
    if json_raises:
        resp.json.side_effect = json.JSONDecodeError("Expecting value", text or "<html>", 0)
    else:
        resp.json.return_value = json_value
    resp.text = text
    return resp


def test_non_json_success_response_raises_clean_error():
    """A 200 whose body is not JSON (captive portal / WAF interstitial) must
    surface as a clean ModrinthApiError, not a raw JSONDecodeError."""
    client = ModrinthClient()
    client.session = MagicMock()
    client.session.request.return_value = _fake_response(
        status=200, json_raises=True, text="<html>captive portal</html>"
    )

    with pytest.raises(ModrinthApiError):
        client.get_project("sodium")


def test_json_success_response_returned_unchanged():
    """A valid JSON 200 is parsed and returned unchanged (pin)."""
    client = ModrinthClient()
    client.session = MagicMock()
    client.session.request.return_value = _fake_response(
        status=200, json_value={"id": "sodium", "title": "Sodium"}
    )

    assert client.get_project("sodium") == {"id": "sodium", "title": "Sodium"}


def test_extract_overrides_rejects_sibling_prefix_escape(tmp_path):
    """A crafted override member whose path resolves into a prefix-sibling of
    the install dir must NOT be written outside the server root.

    The old str.startswith guard treated `.../mc1-evil` as "inside" `.../mc1`
    (shared string prefix); the shared is_within guard rejects it. The write
    path mkdir -p's the parent, so the escape CREATES the sibling dir — a
    pre-existing sibling is not required.
    """
    import io
    import zipfile

    install_path = tmp_path / "mc1"
    install_path.mkdir()
    sibling_escape = tmp_path / "mc1-evil" / "pwn.txt"

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("overrides/config/ok.txt", "ok")
        zf.writestr("overrides/../mc1-evil/pwn.txt", "pwn")
    buf.seek(0)

    client = ModrinthClient()
    with zipfile.ZipFile(buf) as zf:
        client._extract_overrides(zf, install_path, {}, [], [], [], loader="fabric")

    assert not sibling_escape.exists(), "override escaped the server root into a prefix-sibling"
    assert (install_path / "config" / "ok.txt").read_text() == "ok"
