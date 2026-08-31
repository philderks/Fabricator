"""Every /api/ route must be classified in the MCP permission table.

This is the mechanism that forces a new route to be bucketed: add an /api/
route without a BUCKETS entry and ``test_every_api_rule_is_bucketed`` goes RED.
"""
from __future__ import annotations

from collections import Counter

from backend.auth.buckets import BUCKETS


def _live_api_pairs(app):
    pairs = set()
    for rule in app.url_map.iter_rules():
        if not rule.rule.startswith("/api/"):
            continue  # exclude the SPA catch-alls (serve_frontend at "/" etc.)
        for method in rule.methods - {"HEAD", "OPTIONS"}:  # Flask auto-adds these
            pairs.add((method, rule.rule))
    return pairs


def test_every_api_rule_is_bucketed(app):
    uncovered = sorted(_live_api_pairs(app) - set(BUCKETS))
    assert not uncovered, f"unclassified /api/ routes: {uncovered}"


def test_no_stale_bucket_entries(app):
    stale = sorted(set(BUCKETS) - _live_api_pairs(app))
    assert not stale, f"BUCKETS entries for routes that no longer exist: {stale}"


def test_bucket_values_are_valid():
    assert set(BUCKETS.values()) <= {"read", "manage", "never"}


def test_manage_bucket_is_exactly_the_expected_set():
    manage = {k for k, v in BUCKETS.items() if v == "manage"}
    expected = {
        ("POST", "/api/servers/<server_id>/start"),
        ("POST", "/api/servers/<server_id>/stop"),
        ("POST", "/api/servers/<server_id>/restart"),
        ("POST", "/api/servers/<server_id>/install"),
        ("POST", "/api/modrinth/mod/<mod_id>/install"),
        ("DELETE", "/api/servers/<server_id>/mods"),
        ("DELETE", "/api/servers/<server_id>/mods/<path:filename>"),
    }
    assert manage == expected


def test_read_and_manage_counts():
    counts = Counter(BUCKETS.values())
    assert counts["read"] == 32
    assert counts["manage"] == 7
    assert counts["never"] == 60
    assert sum(counts.values()) == 99


def test_the_console_and_settings_routes_are_never():
    # Spot-check the archetype hazards are denied to every token.
    assert BUCKETS[("POST", "/api/servers/<server_id>/console")] == "never"
    assert BUCKETS[("PUT", "/api/servers/<server_id>/settings")] == "never"
    assert BUCKETS[("GET", "/api/servers/<server_id>/files/content")] == "never"
