"""/api/java/status flat fields must report the EFFECTIVE Java start would use.

The start path resolves its JVM via ``_resolve_java_exec`` (explicit
``javaPath`` -> ``find_compatible_java`` (system-if-sufficient -> managed) ->
``'java'`` on PATH). The status endpoint's top-level flat fields (``installed``,
``version``, ``detected_major``, ``meets_requirement``) historically probed
only the ``java_path`` param-or-PATH ``java`` — so a host with managed Java
installed but no/old system Java misreported "not installed / requirement
unmet" while start would succeed.

These tests lock the fix: without an explicit ``java_path`` param and with a
known required major, the flat fields derive from
``find_compatible_java(required) or 'java'`` (the ``or 'java'`` mirrors the
registry's start fallback, so present-but-too-old system Java keeps being
reported). The ``system_java`` block stays a PATH-only probe — the semantic
split between "effective Java" (flat) and "system Java" (block) is pinned
here. With an explicit ``java_path`` param, or without a resolvable required
major, behavior is byte-identical to before (PATH/param probe,
``find_compatible_java`` never consulted).
"""
from __future__ import annotations

import subprocess
from unittest.mock import patch


MANAGED_PATH = "/managed/jdk-21/bin/java"

_FAKE_ASSET = {
    "download_url": "https://example.invalid/temurin21.tar.gz",
    "filename": "temurin21.tar.gz",
    "size_bytes": 1,
    "checksum_algorithm": "sha256",
    "install_major": 21,
    "substituted": False,
}


def _version_output(major: int) -> str:
    return f'openjdk version "{major}.0.4" 2024-07-16'


def _fake_run(system_major=None, managed_major=None):
    """Build a ``subprocess.run`` fake discriminating on argv[0].

    ``system_major=None`` -> PATH ``java`` raises FileNotFoundError (absent).
    ``managed_major`` covers any non-``'java'`` binary path (the managed
    install or an explicit ``java_path`` param).
    """

    def run(argv, **kwargs):
        binary = argv[0]
        major = system_major if binary == "java" else managed_major
        if major is None:
            raise FileNotFoundError(binary)
        return subprocess.CompletedProcess(
            argv, 0, stdout="", stderr=_version_output(major)
        )

    return run


def _get_status(client, query: str) -> dict:
    response = client.get(f"/api/java/status{query}")
    assert response.status_code == 200
    return response.get_json()


def _patched(find_return, system_major=None, managed_major=None):
    """Patch the two seams: the version probe and the start-path resolver."""
    return (
        patch("subprocess.run", side_effect=_fake_run(system_major, managed_major)),
        patch(
            "backend.server.java_manager.find_compatible_java",
            return_value=find_return,
        ),
        patch(
            "backend.server.java_manager.adoptium_asset_url",
            return_value=dict(_FAKE_ASSET),
        ),
    )


# ---------------------------------------------------------------------------
# Behavioral (RED before the fix)
# ---------------------------------------------------------------------------

def test_managed_only_flat_fields_report_managed(client):
    """No system Java, managed 21 present -> flat fields say installed/21/met."""
    run_p, find_p, asset_p = _patched(
        MANAGED_PATH, system_major=None, managed_major=21
    )
    with run_p, find_p as find_mock, asset_p:
        body = _get_status(client, "?required_java=21")
    find_mock.assert_called_once_with(21)
    assert body["installed"] is True
    assert body["detected_major"] == 21
    assert body["version"] is not None
    assert body["meets_requirement"] is True
    assert body["java_path"] == MANAGED_PATH


def test_both_prefers_start_resolution(client):
    """System 17 (too old) + managed 21 -> flat fields follow the managed 21."""
    run_p, find_p, asset_p = _patched(
        MANAGED_PATH, system_major=17, managed_major=21
    )
    with run_p, find_p, asset_p:
        body = _get_status(client, "?required_java=21")
    assert body["installed"] is True
    assert body["detected_major"] == 21
    assert body["meets_requirement"] is True


def test_system_java_block_stays_path_only(client):
    """THE semantic-split pin: managed active, system_java still PATH truth."""
    run_p, find_p, asset_p = _patched(
        MANAGED_PATH, system_major=17, managed_major=21
    )
    with run_p, find_p, asset_p:
        body = _get_status(client, "?required_java=21")
    # Flat = effective (managed) ...
    assert body["detected_major"] == 21
    assert body["meets_requirement"] is True
    # ... while the system_java block keeps reporting PATH java only.
    assert body["system_java"] == {
        "path": "java",
        "version": 17,
        "meets_requirement": False,
    }


# ---------------------------------------------------------------------------
# Pins (GREEN before and after — lock unchanged behavior)
# ---------------------------------------------------------------------------

def test_system_only_unchanged(client):
    """System java satisfies the requirement -> identical to old behavior."""
    run_p, find_p, asset_p = _patched("java", system_major=21)
    with run_p, find_p, asset_p:
        body = _get_status(client, "?required_java=21")
    assert body["installed"] is True
    assert body["detected_major"] == 21
    assert body["meets_requirement"] is True
    assert body["java_path"] == "java"
    assert body["system_java"]["version"] == 21
    assert body["system_java"]["meets_requirement"] is True


def test_neither_falls_back_to_path_probe(client):
    """No compatible java anywhere -> mirror the registry's ``or 'java'``.

    System java exists but is too old and no managed install: start would fall
    back to PATH java (and fail its guard) — status must keep reporting that
    present-but-too-old binary, not "not installed".
    """
    run_p, find_p, asset_p = _patched(None, system_major=17)
    with run_p, find_p, asset_p:
        body = _get_status(client, "?required_java=21")
    assert body["installed"] is True
    assert body["detected_major"] == 17
    assert body["meets_requirement"] is False
    assert body["java_path"] == "java"


def test_explicit_java_path_param_unchanged(client):
    """?java_path= wins (start precedence 1); resolver never consulted."""
    run_p, find_p, asset_p = _patched(
        MANAGED_PATH, system_major=None, managed_major=21
    )
    with run_p, find_p as find_mock, asset_p:
        body = _get_status(client, "?required_java=21&java_path=/custom/java")
    find_mock.assert_not_called()
    assert body["installed"] is True
    assert body["detected_major"] == 21
    assert body["java_path"] == "/custom/java"
    assert body["system_java"]["path"] == "/custom/java"


def test_required_unknown_probes_path(client):
    """No resolvable required major -> PATH probe, resolver never consulted.

    Without a version there is no "effective Java start would use"
    (``find_compatible_java`` needs a major), so behavior stays byte-identical
    to the old endpoint: probe PATH ``java``; ``meets_requirement`` False by
    the unchanged formula.
    """
    run_p, find_p, asset_p = _patched(None, system_major=21)
    with run_p, find_p as find_mock, asset_p:
        body = _get_status(client, "")
    find_mock.assert_not_called()
    assert body["installed"] is True
    assert body["detected_major"] == 21
    assert body["required_java"] is None
    assert body["meets_requirement"] is False
    assert body["java_path"] == "java"
