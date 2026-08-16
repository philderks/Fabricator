"""Route permission buckets for MCP API-token access.

Keyed on ``(METHOD, url_rule.rule)`` — the Flask routing pattern, never the raw
request path — so ``<server_id>`` and friends match. Values:

  * ``"read"``   — reachable by a ``read`` OR a ``manage`` token.
  * ``"manage"`` — reachable by a ``manage`` token only.
  * ``"never"``  — reachable by NO token, either scope. Also covers the
                   ``/api/<path:_>`` catch-all, so an unknown path denies.

The companion test ``tests/test_url_map_bucket_coverage.py`` fails RED if any
``/api/`` rule in the live ``url_map`` is missing here, so a new route cannot
ship unclassified.
"""
from __future__ import annotations

# --- READ: safe for a `read` (or `manage`) token ---------------------------- #
_READ = [
    ("GET", "/api/health"),
    ("GET", "/api/servers"),
    ("GET", "/api/servers/<server_id>"),
    ("GET", "/api/servers/<server_id>/logs"),
    ("GET", "/api/servers/<server_id>/mods"),
    ("GET", "/api/servers/<server_id>/install/progress"),
    ("GET", "/api/servers/<server_id>/metrics"),
    ("GET", "/api/metrics/system"),
    ("GET", "/api/java/status"),
    ("GET", "/api/java/installed"),
    ("GET", "/api/java/install/progress/<task_id>"),
    ("GET", "/api/loaders/<loader>/versions/game"),
    ("GET", "/api/loaders/<loader>/versions/loader"),
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
    ("GET", "/api/modrinth/version/<version_id>"),
    # Identifies the mods folder's jars against Modrinth by content hash.
    # Audited CLEAN: no caller input reaches a path (the folder comes from the
    # stored record), the upstream host is fixed, and the response is bare
    # filenames plus public catalog metadata.
    ("GET", "/api/modrinth/servers/<server_id>/resolve-installed"),
    ("GET", "/api/servers/<server_id>/snapshots"),
    ("GET", "/api/servers/<server_id>/backup-summary"),
    ("GET", "/api/servers/<server_id>/backup-configs"),
    ("GET", "/api/backup-jobs/<job_id>"),
    ("GET", "/api/auth/status"),
]

# --- MANAGE: `manage` token only -------------------------------------------- #
_MANAGE = [
    ("POST", "/api/servers/<server_id>/start"),
    ("POST", "/api/servers/<server_id>/stop"),
    ("POST", "/api/servers/<server_id>/restart"),
    ("POST", "/api/servers/<server_id>/install"),
    ("POST", "/api/modrinth/mod/<mod_id>/install"),
    ("DELETE", "/api/servers/<server_id>/mods"),
    ("DELETE", "/api/servers/<server_id>/mods/<path:filename>"),
]

# --- NEVER: no token, either scope ------------------------------------------ #
_NEVER = [
    # raw console / file read+write / boot behaviour / delete / create
    ("POST", "/api/servers/<server_id>/console"),
    ("GET", "/api/servers/<server_id>/files"),
    ("GET", "/api/servers/<server_id>/files/content"),
    ("GET", "/api/servers/<server_id>/files/search"),
    ("PUT", "/api/servers/<server_id>/files/content"),
    ("PUT", "/api/servers/<server_id>/autostart"),
    ("DELETE", "/api/servers/<server_id>"),
    ("POST", "/api/servers"),
    # host-level java
    ("POST", "/api/java/install"),
    ("DELETE", "/api/java/install/<task_id>"),
    ("DELETE", "/api/java/installed/<int:major>"),
    # self-update (status included: part of the update surface)
    ("POST", "/api/system/update"),
    ("GET", "/api/system/update/status"),
    # playit (whole surface)
    ("POST", "/api/playit/start"),
    ("POST", "/api/playit/stop"),
    ("POST", "/api/playit/reset"),
    ("GET", "/api/playit/status"),
    # backups: exfil / file-overwrite / destructive (snapshot delete included)
    ("GET", "/api/servers/<server_id>/snapshots/<snapshot_id>/download"),
    ("POST", "/api/servers/<server_id>/snapshots/<snapshot_id>/restore"),
    ("DELETE", "/api/servers/<server_id>/snapshots/<snapshot_id>"),
    ("POST", "/api/servers/<server_id>/world-import"),
    # settings (unfiltered record merge + server.properties rewrite)
    ("PUT", "/api/servers/<server_id>/settings"),
    # backup schedule / quick (caller-chosen storagePath write-location)
    ("POST", "/api/servers/<server_id>/backup-configs"),
    ("PUT", "/api/servers/<server_id>/backup-configs/<config_id>"),
    ("DELETE", "/api/servers/<server_id>/backup-configs/<config_id>"),
    ("POST", "/api/servers/<server_id>/backup-configs/<config_id>/run"),
    ("POST", "/api/servers/<server_id>/backup-quick"),
    # full-server migration is intentionally UI-only until a dedicated MCP tool
    # can present its backup and rollback contract.
    ("POST", "/api/servers/<server_id>/upgrade"),
    # modpack install (can plant files including an @args_file)
    ("POST", "/api/modrinth/modpack/<project_id>/install"),
    # .mrpack upload surface: the caller supplies the archive outright, so the
    # install is the same file-planting reach with none of the catalog's
    # vetting. Discard is listed with them to keep the surface whole.
    ("POST", "/api/modrinth/modpack/upload"),
    ("POST", "/api/modrinth/modpack/upload/<upload_id>/install"),
    ("DELETE", "/api/modrinth/modpack/upload/<upload_id>"),
    # players reads: personal data (names, UUIDs, IP addresses, per-player
    # "last seen"). No redaction makes these safe to hand an assistant, and they
    # answer no question the diagnosis use case asks.
    ("GET", "/api/servers/<server_id>/players/state"),
    ("GET", "/api/servers/<server_id>/players/online"),
    # players surface (bans / kick / ops / whitelist)
    ("POST", "/api/servers/<server_id>/players/bans"),
    ("DELETE", "/api/servers/<server_id>/players/bans"),
    ("POST", "/api/servers/<server_id>/players/bans/ip"),
    ("DELETE", "/api/servers/<server_id>/players/bans/ip"),
    ("POST", "/api/servers/<server_id>/players/kick"),
    ("POST", "/api/servers/<server_id>/players/ops"),
    ("PATCH", "/api/servers/<server_id>/players/ops"),
    ("DELETE", "/api/servers/<server_id>/players/ops"),
    ("POST", "/api/servers/<server_id>/players/whitelist"),
    ("DELETE", "/api/servers/<server_id>/players/whitelist"),
    ("PATCH", "/api/servers/<server_id>/players/whitelist/active"),
    ("PATCH", "/api/servers/<server_id>/players/whitelist/enforce"),
    # auth mutation
    ("POST", "/api/auth/setup"),
    ("POST", "/api/auth/login"),
    ("POST", "/api/auth/change-password"),
    ("POST", "/api/auth/logout"),
    # MCP integration management — a token can never manage tokens or the switch
    ("GET", "/api/integrations/mcp"),
    ("PUT", "/api/integrations/mcp"),
    ("POST", "/api/integrations/mcp/tokens"),
    ("DELETE", "/api/integrations/mcp/tokens/<token_id>"),
    # catch-all: any unknown /api path denies for every token
    ("GET", "/api/<path:_>"),
    ("POST", "/api/<path:_>"),
    ("PUT", "/api/<path:_>"),
    ("DELETE", "/api/<path:_>"),
    ("PATCH", "/api/<path:_>"),
]

BUCKETS = {
    **{key: "read" for key in _READ},
    **{key: "manage" for key in _MANAGE},
    **{key: "never" for key in _NEVER},
}
