"""Context economy, and the honest limits of the mods listing.

The assertions about credentials here are defence in depth and are labelled as
such: the panel already strips them server-side for every token caller. These
tests would still pass if this module did nothing about secrets, because the
values never arrive. They exist so a future change that starts echoing whatever
the panel sends gets a second look.
"""
from __future__ import annotations

import pytest

from fabricator_mcp.projection import (
    MAX_LOG_LINE_CHARS,
    merge_hash_identification,
    project_log_lines,
    project_mod_entry,
    project_server,
)
from fabricator_mcp.tools.read import MODS_LISTING_NOTE


def test_server_projection_keeps_the_diagnosis_fields():
    projected = project_server({
        "id": "s1", "name": "pack", "loader": "fabric", "version": "1.20.1",
        "status": "running", "port": 25565, "maxPlayers": 20,
        "runtime": {"status": "running", "ram": 2048, "pid": 42, "mods": 118},
    })
    assert projected["id"] == "s1"
    assert projected["runtime"]["mods"] == 118


def test_server_projection_drops_noise_the_agent_never_asked_for():
    projected = project_server({
        "id": "s1",
        "motd": "hello", "difficulty": "normal", "levelName": "world",
        "spawnProtection": 16, "viewDistance": 10,
    })
    assert set(projected) == {"id"}


def test_server_projection_would_not_echo_a_credential():
    """Defence in depth. The panel already removed these before we saw them."""
    projected = project_server({"id": "s1", "rconPassword": "hunter2", "installPath": "/srv/x"})
    assert "rconPassword" not in projected
    assert "installPath" not in projected
    assert "hunter2" not in str(projected)


def test_log_lines_are_ordered_and_tagged_by_stream():
    projected = project_log_lines({
        "running": True,
        "stdout": [{"ts": "2", "text": "b"}],
        "stderr": [{"ts": "1", "text": "a"}],
    }, limit=10)
    assert [line["text"] for line in projected["lines"]] == ["a", "b"]
    assert projected["lines"][0]["stream"] == "stderr"


def test_a_single_enormous_log_line_is_truncated():
    projected = project_log_lines(
        {"stdout": [{"ts": "1", "text": "x" * (MAX_LOG_LINE_CHARS + 500)}]}, limit=10
    )
    text = projected["lines"][0]["text"]
    assert len(text) < MAX_LOG_LINE_CHARS + 50
    assert text.endswith("[truncated]")


def test_log_limit_takes_the_newest_lines():
    payload = {"stdout": [{"ts": str(i), "text": f"line{i}"} for i in range(1, 6)]}
    projected = project_log_lines(payload, limit=2)
    assert [line["text"] for line in projected["lines"]] == ["line4", "line5"]


def test_mod_entry_is_removable_when_the_name_is_a_plain_filename():
    entry = project_mod_entry({"name": "sodium.jar", "size": 10})
    assert entry["removable"] is True
    assert "removalNote" not in entry


@pytest.mark.parametrize("name", ["nested/sodium.jar", "nested\\sodium.jar"])
def test_mod_entry_that_cannot_be_a_delete_handle_says_so(name):
    """A4: report the limitation honestly rather than working around the filter."""
    entry = project_mod_entry({"name": name})
    assert entry["removable"] is False
    assert "panel UI" in entry["removalNote"]


def test_mod_entry_carries_the_install_manifest_when_the_panel_has_one():
    entry = project_mod_entry({
        "name": "sodium.jar",
        "modrinth": {"projectId": "AANobbMI", "title": "Sodium", "versionNumber": "0.5.8"},
    })
    assert entry["projectId"] == "AANobbMI"
    assert entry["source"] == "manifest"


def test_the_manifest_wins_over_the_hash_lookup():
    """What the panel actually installed beats what a hash infers."""
    mods = [project_mod_entry({"name": "a.jar", "modrinth": {"projectId": "REAL"}})]
    merged = merge_hash_identification(mods, {"a.jar": {"projectId": "GUESS"}})
    assert merged[0]["projectId"] == "REAL"
    assert merged[0]["source"] == "manifest"


def test_the_hash_lookup_fills_a_gap_the_manifest_does_not_cover():
    mods = [project_mod_entry({"name": "handdropped.jar"})]
    merged = merge_hash_identification(mods, {"handdropped.jar": {"projectId": "FOUND"}})
    assert merged[0]["projectId"] == "FOUND"
    assert merged[0]["source"] == "hash"


def test_the_listing_note_states_what_the_listing_cannot_show():
    assert "subfolder" in MODS_LISTING_NOTE
    assert "panel UI" in MODS_LISTING_NOTE
