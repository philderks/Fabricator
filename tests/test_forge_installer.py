"""ForgeInstaller — Forge promotions-API + Maven-backed installer.

Phase 3b.1 T1 covers the version-listing layer; T2 fills in the install
body with era dispatch (legacy single-jar vs modern args_file).
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def fake_promotions():
    """A representative slice of the Forge promotions_slim.json response.

    Covers all four eras: 1.7.10 (legacy, both pointers identical),
    1.12.2 (legacy, recommended != latest), 1.16.5 (legacy/transition),
    1.20.1 (modern), 1.21.4 (modern, current). Plus 1.18.1 with ONLY
    a latest pointer (no recommended) — common edge case during a Forge
    transition window.
    """
    return {
        "homepage": "https://files.minecraftforge.net/...",
        "promos": {
            "1.7.10-latest": "10.13.4.1614",
            "1.7.10-recommended": "10.13.4.1614",
            "1.12.2-latest": "14.23.5.2864",
            "1.12.2-recommended": "14.23.5.2859",
            "1.16.5-latest": "36.2.42",
            "1.16.5-recommended": "36.2.34",
            "1.18.1-latest": "39.1.2",
            "1.20.1-latest": "47.4.20",
            "1.20.1-recommended": "47.4.10",
            "1.21.4-latest": "54.1.16",
            "1.21.4-recommended": "54.1.14",
        },
    }


def _patch_session(installer, *, promotions=None, raise_exc=None):
    """Stub installer.session.get to return canned promotions or raise."""
    session = MagicMock()

    def get(url, **_):
        if raise_exc is not None:
            raise raise_exc
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        if "promotions_slim.json" in url:
            resp.json.return_value = promotions
        return resp

    session.get.side_effect = get
    installer.session = session
    return session


def test_loader_name(tmp_path):
    from backend.server.installer.forge import ForgeInstaller
    assert ForgeInstaller(tmp_path).loader_name == "forge"


def test_requires_java_for_install_is_true(tmp_path):
    from backend.server.installer.forge import ForgeInstaller
    assert ForgeInstaller(tmp_path).requires_java_for_install is True


def test_get_minecraft_versions_dedups_and_sorts(tmp_path, fake_promotions):
    """Each MC version surfaces once, sorted descending (newest first)."""
    from backend.server.installer.forge import ForgeInstaller
    inst = ForgeInstaller(tmp_path)
    _patch_session(inst, promotions=fake_promotions)

    versions = inst.get_minecraft_versions()
    raw = [v["version"] for v in versions]

    # Each MC version appears once (no duplicates from -latest/-recommended).
    assert raw == [
        "1.21.4",
        "1.20.1",
        "1.18.1",
        "1.16.5",
        "1.12.2",
        "1.7.10",
    ]
    # All Forge releases are stable (no pre-release / snapshot concept here).
    assert all(v["stable"] is True for v in versions)
    assert all(v["type"] == "release" for v in versions)


def test_get_available_versions_prefers_recommended_then_latest(
    tmp_path, fake_promotions
):
    """When both pointers exist, return [recommended, latest] in that order."""
    from backend.server.installer.forge import ForgeInstaller
    inst = ForgeInstaller(tmp_path)
    _patch_session(inst, promotions=fake_promotions)

    versions = inst.get_available_versions("1.20.1")
    raw = [v["version"] for v in versions]
    # Recommended first (the "preferred" stable build), then latest.
    assert raw == ["47.4.10", "47.4.20"]
    assert all(v["stable"] is True for v in versions)


def test_get_available_versions_latest_only_when_no_recommended(
    tmp_path, fake_promotions
):
    """1.18.1 in the fixture has only -latest. Surface that one alone."""
    from backend.server.installer.forge import ForgeInstaller
    inst = ForgeInstaller(tmp_path)
    _patch_session(inst, promotions=fake_promotions)

    versions = inst.get_available_versions("1.18.1")
    raw = [v["version"] for v in versions]
    assert raw == ["39.1.2"]


def test_get_available_versions_unknown_mc_returns_empty(
    tmp_path, fake_promotions
):
    from backend.server.installer.forge import ForgeInstaller
    inst = ForgeInstaller(tmp_path)
    _patch_session(inst, promotions=fake_promotions)

    assert inst.get_available_versions("1.5.2") == []
    assert inst.get_available_versions(None) == []


def test_get_minecraft_versions_returns_empty_on_meta_failure(tmp_path):
    """Network error or malformed JSON → clean [], not an exception."""
    import requests
    from backend.server.installer.forge import ForgeInstaller
    inst = ForgeInstaller(tmp_path)
    _patch_session(inst, raise_exc=requests.RequestException("boom"))

    assert inst.get_minecraft_versions() == []


def test_install_stub_returns_failure(tmp_path):
    """T1 ships only the stub. T2 fills in the real install."""
    from backend.server.installer.forge import ForgeInstaller
    inst = ForgeInstaller(tmp_path)
    result = inst.install("1.20.1")
    assert result.success is False
    assert "not yet implemented" in result.message.lower() or \
           "not implemented" in result.message.lower()
