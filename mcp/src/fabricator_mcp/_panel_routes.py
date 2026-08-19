"""A snapshot of the panel's route permission table — vendored on purpose.

The island is installed on a user's machine where ``backend/`` does not exist,
so the panel's table cannot be a runtime import. This file is that table, copied
by hand, and ``tests/test_panel_drift.py`` fails when it stops matching the
panel.

WHEN THIS FILE AND THE PANEL DISAGREE, THE ANSWER IS NOT TO RE-COPY IT.
A route that moved INTO read/manage must be audited with both lenses before any
tool uses it. A route that moved OUT (to never) means a tool is now wrong and
must be removed or re-pointed. There is deliberately no auto-sync script: it
would turn a security decision into a mechanical edit, which is the exact
failure the route audit exists to prevent.

Bump ``PANEL_TABLE_REVISION`` only after a human has re-audited the difference.
"""
from __future__ import annotations

#: Date of the last human re-audit of this snapshot.
PANEL_TABLE_REVISION = "2026-08-19"

PANEL_READ: frozenset[tuple[str, str]] = frozenset({
    ("GET", "/api/auth/status"),
    ("GET", "/api/backup-jobs/<job_id>"),
    ("GET", "/api/health"),
    ("GET", "/api/java/install/progress/<task_id>"),
    ("GET", "/api/java/installed"),
    ("GET", "/api/java/status"),
    ("GET", "/api/loaders/<loader>/versions/game"),
    ("GET", "/api/loaders/<loader>/versions/loader"),
    ("GET", "/api/metrics/system"),
    ("GET", "/api/modrinth/categories"),
    ("GET", "/api/modrinth/game-versions"),
    ("GET", "/api/modrinth/loaders"),
    ("GET", "/api/modrinth/mod/<mod_id>"),
    ("GET", "/api/modrinth/mod/<mod_id>/download-url"),
    ("GET", "/api/modrinth/mod/<mod_id>/versions"),
    ("GET", "/api/modrinth/modpack/install-progress/<server_id>"),
    ("GET", "/api/modrinth/modpacks/search"),
    ("GET", "/api/modrinth/project/<project_id>"),
    ("GET", "/api/modrinth/project/<project_id>/resolve-version"),
    ("GET", "/api/modrinth/project/<project_id>/versions"),
    ("GET", "/api/modrinth/search"),
    ("GET", "/api/modrinth/servers/<server_id>/resolve-installed"),
    ("GET", "/api/modrinth/version/<version_id>"),
    ("GET", "/api/servers"),
    ("GET", "/api/servers/<server_id>"),
    ("GET", "/api/servers/<server_id>/backup-configs"),
    ("GET", "/api/servers/<server_id>/backup-summary"),
    ("GET", "/api/servers/<server_id>/install/progress"),
    ("GET", "/api/servers/<server_id>/java-status"),
    ("GET", "/api/servers/<server_id>/logs"),
    ("GET", "/api/servers/<server_id>/metrics"),
    ("GET", "/api/servers/<server_id>/mods"),
    ("GET", "/api/servers/<server_id>/snapshots"),
})

PANEL_MANAGE: frozenset[tuple[str, str]] = frozenset({
    ("DELETE", "/api/servers/<server_id>/mods"),
    ("DELETE", "/api/servers/<server_id>/mods/<path:filename>"),
    ("POST", "/api/modrinth/mod/<mod_id>/install"),
    ("POST", "/api/servers/<server_id>/install"),
    ("POST", "/api/servers/<server_id>/restart"),
    ("POST", "/api/servers/<server_id>/start"),
    ("POST", "/api/servers/<server_id>/stop"),
})

#: Every route a token may reach, either scope.
PANEL_TOKEN_REACHABLE = PANEL_READ | PANEL_MANAGE
