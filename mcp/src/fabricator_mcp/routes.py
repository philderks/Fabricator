"""The tool-to-route mapping, as data.

Every tool this package advertises appears here with the exact panel routes it
calls and the scope it needs. Keeping it as a table rather than scattering the
paths through handler code is what lets a test assert the whole surface at once:
that no tool reaches outside what a token may touch, and that no ``manage``
route is reachable from a tool the package calls ``read``.

The set is deliberately NARROWER than what the token can reach. Tools are a
curation layer, chosen for one job — working out why a modpack server is
crashing — not a mirror of the panel's API. Routes the panel permits and this
package deliberately does not use are listed in the plan's tempted-to-widen log.
"""
from __future__ import annotations

READ = "read"
MANAGE = "manage"

#: tool name -> the (METHOD, rule) pairs it calls, in the order it calls them.
TOOL_ROUTES: dict[str, tuple[tuple[str, str], ...]] = {
    # --- read ---------------------------------------------------------------
    "list_servers": (
        ("GET", "/api/servers"),
    ),
    "get_server": (
        ("GET", "/api/servers/<server_id>"),
    ),
    "read_server_logs": (
        ("GET", "/api/servers/<server_id>/logs"),
    ),
    "list_installed_mods": (
        ("GET", "/api/servers/<server_id>/mods"),
        # only when identify=True
        ("GET", "/api/modrinth/servers/<server_id>/resolve-installed"),
    ),
    "check_resource_usage": (
        ("GET", "/api/servers/<server_id>/metrics"),
        ("GET", "/api/metrics/system"),
    ),
    "check_java": (
        ("GET", "/api/java/status"),
        ("GET", "/api/java/installed"),
    ),
    "list_loader_game_versions": (
        ("GET", "/api/loaders/<loader>/versions/game"),
    ),
    "list_loader_versions": (
        ("GET", "/api/loaders/<loader>/versions/loader"),
    ),
    "get_backup_status": (
        ("GET", "/api/servers/<server_id>/backup-summary"),
    ),
    "list_snapshots": (
        ("GET", "/api/servers/<server_id>/snapshots"),
    ),
    "get_install_progress": (
        ("GET", "/api/servers/<server_id>/install/progress"),
    ),
    "search_modpacks": (("GET", "/api/modrinth/modpacks/search"),),
    "get_mod_version": (("GET", "/api/modrinth/version/<version_id>"),),
    "check_installed_mod_updates": (
        ("GET", "/api/servers/<server_id>"),
        ("GET", "/api/servers/<server_id>/mods"),
        ("GET", "/api/modrinth/servers/<server_id>/resolve-installed"),
        ("GET", "/api/modrinth/project/<project_id>/resolve-version"),
    ),
    "check_mods_compatibility": (("GET", "/api/modrinth/project/<project_id>/resolve-version"),),
    "get_server_runtime_diagnostics": (
        ("GET", "/api/servers/<server_id>/java-status"),
        ("GET", "/api/servers/<server_id>/install/progress"),
    ),
    "list_backup_configs": (("GET", "/api/servers/<server_id>/backup-configs"),),
    "check_panel": (
        ("GET", "/api/health"),
        ("GET", "/api/auth/status"),
    ),
    "search_modrinth": (
        ("GET", "/api/modrinth/search"),
    ),
    "get_mod_info": (
        ("GET", "/api/modrinth/project/<project_id>"),
        ("GET", "/api/modrinth/project/<project_id>/versions"),
    ),
    "check_mod_compatibility": (
        ("GET", "/api/modrinth/project/<project_id>/resolve-version"),
    ),
    # --- manage -------------------------------------------------------------
    "control_server": (
        ("POST", "/api/servers/<server_id>/start"),
        ("POST", "/api/servers/<server_id>/stop"),
        ("POST", "/api/servers/<server_id>/restart"),
    ),
    "install_server": (
        ("POST", "/api/servers/<server_id>/install"),
    ),
    "update_or_install_mod": (
        ("POST", "/api/modrinth/mod/<mod_id>/install"),
    ),
    "remove_mods": (
        ("DELETE", "/api/servers/<server_id>/mods/<path:filename>"),
        ("DELETE", "/api/servers/<server_id>/mods"),
    ),
}

#: tool name -> the scope a token needs for it.
TOOL_SCOPES: dict[str, str] = {
    "list_servers": READ,
    "get_server": READ,
    "read_server_logs": READ,
    "list_installed_mods": READ,
    "check_resource_usage": READ,
    "check_java": READ,
    "list_loader_game_versions": READ,
    "list_loader_versions": READ,
    "get_backup_status": READ,
    "list_snapshots": READ,
    "get_install_progress": READ,
    "search_modpacks": READ,
    "get_mod_version": READ,
    "check_installed_mod_updates": READ,
    "check_mods_compatibility": READ,
    "get_server_runtime_diagnostics": READ,
    "list_backup_configs": READ,
    "check_panel": READ,
    "search_modrinth": READ,
    "get_mod_info": READ,
    "check_mod_compatibility": READ,
    "control_server": MANAGE,
    "install_server": MANAGE,
    "update_or_install_mod": MANAGE,
    "remove_mods": MANAGE,
}

TOOL_NAMES: tuple[str, ...] = tuple(TOOL_ROUTES)
