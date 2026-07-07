---
title: HTTP API overview
description: High-level map of Fabricator's backend API endpoints.
---

Fabricator's dashboard talks to a Flask API mounted under `/api`. This page is a practical map for contributors and operators; endpoint details may evolve with the UI.

## Auth

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/auth/status` | Return whether auth is enabled, whether setup is needed, and whether the current session is authenticated. |
| `POST` | `/api/auth/setup` | One-time first-boot password setup. JSON only; requires at least 8 characters. |
| `POST` | `/api/auth/login` | Authenticate with the operator password and create a session. |
| `POST` | `/api/auth/logout` | Clear the current authenticated session. |
| `POST` | `/api/auth/change-password` | Change the operator password when it is not env-managed. |

## Health and update

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/health` | Basic health check. |
| `GET` | `/api/update/status` | Current installed/latest Fabricator release status and update progress. |
| `POST` | `/api/update` | Trigger dashboard self-update. |

## playit.gg

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/playit/status` | Return shared tunnel-agent status, claim URL, verification flag, and known playit tunnels. |
| `POST` | `/api/playit/start` | Start the shared playit agent or begin the claim flow. |
| `POST` | `/api/playit/stop` | Stop the shared playit agent and persist the disabled state. |
| `POST` | `/api/playit/reset` | Stop the shared agent and delete the saved playit secret so the next start requires a fresh claim. |

## Servers

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/servers` | List servers with runtime augmentation. |
| `POST` | `/api/servers` | Create a server record. |
| `GET` | `/api/servers/<server_id>` | Get one server with runtime augmentation. |
| `PUT` | `/api/servers/<server_id>/settings` | Update settings and write `server.properties`. |
| `PUT` | `/api/servers/<server_id>/autostart` | Update per-server auto-start behavior. |
| `DELETE` | `/api/servers/<server_id>` | Delete a server record and optionally files. |
| `POST` | `/api/servers/<server_id>/install` | Start async server install. |
| `GET` | `/api/servers/<server_id>/install/progress` | Poll install progress. |
| `POST` | `/api/servers/<server_id>/start` | Start server process. |
| `POST` | `/api/servers/<server_id>/stop` | Stop server process. |
| `POST` | `/api/servers/<server_id>/restart` | Stop then start server process. |
| `GET` | `/api/servers/<server_id>/logs` | Tail process stdout/stderr. |
| `POST` | `/api/servers/<server_id>/console` | Send a command to process stdin. |

## Files and mods

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/servers/<server_id>/files` | Browse a directory below the server root. |
| `GET` | `/api/servers/<server_id>/files/content` | Read a UTF-8 text file. |
| `PUT` | `/api/servers/<server_id>/files/content` | Write a UTF-8 text file. |
| `GET` | `/api/servers/<server_id>/mods` | List installed JARs. |
| `DELETE` | `/api/servers/<server_id>/mods/<filename>` | Delete one installed mod. |
| `DELETE` | `/api/servers/<server_id>/mods` | Bulk delete installed mods. |

## Modrinth

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/modrinth/search` | Search mod projects. |
| `GET` | `/api/modrinth/modpacks/search` | Search modpack projects. |
| `GET` | `/api/modrinth/mod/<mod_id>` | Get mod details. |
| `GET` | `/api/modrinth/project/<project_id>` | Get project details. |
| `GET` | `/api/modrinth/mod/<mod_id>/versions` | List mod versions. |
| `GET` | `/api/modrinth/project/<project_id>/versions` | List project versions. |
| `GET` | `/api/modrinth/project/<project_id>/resolve-version` | Resolve best compatible project version. |
| `GET` | `/api/modrinth/mod/<mod_id>/download-url` | Resolve best compatible mod file URL. |
| `POST` | `/api/modrinth/mod/<mod_id>/install` | Install a Modrinth mod into a server. |
| `POST` | `/api/modrinth/modpack/<project_id>/install` | Install a Modrinth modpack into a server. |
| `GET` | `/api/modrinth/modpack/install-progress/<server_id>` | Poll modpack install progress. |
| `GET` | `/api/modrinth/version/<version_id>` | Get version details. |
| `GET` | `/api/modrinth/categories` | List categories. |
| `GET` | `/api/modrinth/loaders` | List loaders. |
| `GET` | `/api/modrinth/game-versions` | List Minecraft versions. |

## Players

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/servers/<server_id>/players/state` | Combined whitelist/ops/bans/known state. |
| `GET` | `/api/servers/<server_id>/players/online` | Online players from running server. |
| `POST` / `DELETE` | `/api/servers/<server_id>/players/whitelist` | Add/remove whitelist entries. |
| `PATCH` | `/api/servers/<server_id>/players/whitelist/active` | Toggle runtime whitelist. |
| `PATCH` | `/api/servers/<server_id>/players/whitelist/enforce` | Persist stopped-server enforce-whitelist. |
| `POST` / `PATCH` / `DELETE` | `/api/servers/<server_id>/players/ops` | Add, change, or remove operators. |
| `POST` / `DELETE` | `/api/servers/<server_id>/players/bans` | Ban/unban players. |
| `POST` / `DELETE` | `/api/servers/<server_id>/players/bans/ip` | Ban/unban IPs. |
| `POST` | `/api/servers/<server_id>/players/kick` | Kick a player. |

## Backups

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` / `POST` | `/api/servers/<server_id>/backup-configs` | List/create backup configs. |
| `PUT` / `DELETE` | `/api/servers/<server_id>/backup-configs/<config_id>` | Update/delete a backup config. |
| `POST` | `/api/servers/<server_id>/backup-configs/<config_id>/run` | Run a configured backup now. |
| `POST` | `/api/servers/<server_id>/backup-quick` | Run an ad-hoc backup. |
| `GET` | `/api/servers/<server_id>/backup-summary` | Snapshot count, size, last/next run. |
| `GET` | `/api/servers/<server_id>/snapshots` | List snapshots. |
| `DELETE` | `/api/servers/<server_id>/snapshots/<snapshot_id>` | Delete snapshot record/archive. |
| `GET` | `/api/servers/<server_id>/snapshots/<snapshot_id>/download` | Download snapshot as tar or zip. |
| `POST` | `/api/servers/<server_id>/snapshots/<snapshot_id>/restore` | Start restore job. |
| `POST` | `/api/servers/<server_id>/world-import` | Upload a world archive and start a world-import job. |
| `GET` | `/api/backup-jobs/<job_id>` | Poll backup/restore/world-import job. |

## Java, metrics, and loaders

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/java/status` | Java runtime status and recommendations. |
| `POST` | `/api/java/install` | Start managed Java install. |
| `GET` | `/api/java/install/progress/<task_id>` | Poll Java install progress. |
| `DELETE` | `/api/java/install/<task_id>` | Cancel Java install task. |
| `GET` | `/api/java/installed` | List managed Java runtimes installed on disk. |
| `DELETE` | `/api/java/installed/<major>` | Delete an installed managed Java major version. |
| `GET` | `/api/metrics/system` | Host-level CPU/RAM metrics when available. |
| `GET` | `/api/servers/<server_id>/metrics` | Per-server runtime metrics when available. |
| `GET` | `/api/loaders/<loader>/versions/game` | Supported Minecraft versions for a loader. |
| `GET` | `/api/loaders/<loader>/versions/loader` | Loader-specific versions for a Minecraft version. |
