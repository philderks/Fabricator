# Fabricator — API Documentation

REST API reference for the Fabricator Minecraft server manager. Every endpoint lives under `/api`
and returns JSON, with two deliberate exceptions: snapshot download streams a binary archive
attachment, and world import takes raw archive bytes as its request body. Unknown `/api/...` paths
return `404 {"error": "endpoint not found", "path": ...}` rather than the SPA's HTML.

Errors are consistently `{"error": "<message>"}`. Anything under `/api` not listed as public in
[Authentication](#authentication) requires a session.

## Contents

- [Authentication](#authentication)
- [Health](#health)
- [Servers](#servers)
- [Server files](#server-files)
- [Mods](#mods)
- [Console & metrics](#console--metrics)
- [Loader versions](#loader-versions)
- [Java management](#java-management)
- [Players](#players)
- [Backups & snapshots](#backups--snapshots)
- [Modrinth integration](#modrinth-integration)
- [playit.gg tunnel](#playitgg-tunnel)
- [System updates](#system-updates)
- [Configuration](#configuration)
- [Loader registry (developers)](#loader-registry-developers)
- [Modrinth client (Python)](#modrinth-client-python)
- [Worked examples](#worked-examples)
- [Testing](#testing)
- [Security notes](#security-notes)

---

## Authentication

Fabricator ships with a single-operator password login. The gate is default-deny: every `/api/`
route requires an authenticated session except the ones listed below.

**States**

- **Disabled** — `FABRICATOR_DISABLE_AUTH=1`. The gate passes everything through.
- **Setup mode** — auth is enabled but no credential exists yet. The app boots locked and only
  serves `POST /api/auth/setup`, `GET /api/auth/status` and `GET /api/health` until a password is set.
- **Configured** — normal login. Public routes are `POST /api/auth/login`, `GET /api/auth/status`
  and `GET /api/health`; everything else needs the session cookie.

Unauthenticated requests get `401 {"error": "authentication required"}` (or `{"error": "setup required"}`
in setup mode). The session cookie is HttpOnly, SameSite=Lax, and lives for 7 days.

#### `POST /api/auth/setup`

First-boot only: sets the operator password and logs the caller in. JSON body required.

**Body:** `{ "password": "at-least-8-chars" }`

**Response (200):** `{ "authenticated": true }`
**Errors:** `400` invalid/short password or non-JSON body · `409 {"error": "already configured"}`

#### `POST /api/auth/login`

**Body:** `{ "password": "..." }`

**Response (200):** `{ "authenticated": true }`
**Errors:** `400` password missing · `401 {"error": "invalid credentials"}` (delayed ~1s)

#### `POST /api/auth/change-password`

Requires an active session **and** the current password.

**Body:** `{ "current": "...", "new": "at-least-8-chars" }`

**Response (200):** `{ "changed": true }`
**Errors:** `400` missing fields or new password too short · `401` current password incorrect ·
`409` when the password is managed via `FABRICATOR_AUTH_PASSWORD_HASH`

#### `POST /api/auth/logout`

Clears the session. **Response (200):** `{ "authenticated": false }`

#### `GET /api/auth/status`

**Response (200):**
```json
{ "enabled": true, "authenticated": false, "needs_setup": false }
```

---

## Health

#### `GET /api/health`

**Response (200):** `{ "healthy": true }`

---

## Servers

#### `GET /api/servers`

List all servers. Each record is augmented with a `runtime` block from the process registry
(live status, PID, RAM, mod count).

#### `POST /api/servers`

Create a server record. This only registers the server — call `/install` afterwards to lay down
the files.

**Required fields:** `name`, `version`, `loader`, `port`, `installPath`

**Response (201):** the created server, including a `javaRequirement` block describing the
required Java major, what was detected, and a `recommended_install` download hint.

**Errors:** `400` missing fields or the port is already used by another server · `500` on write failure

#### `GET /api/servers/<server_id>`

Single server, augmented with runtime state. `404` if unknown.

#### `PUT /api/servers/<server_id>/settings`

Update server settings and rewrite `server.properties`. `id` and `createdAt` are ignored if sent.

**Errors:** `409` if the server is running (stop it first) · `404` unknown server · `500` if
`server.properties` cannot be written

#### `PUT /api/servers/<server_id>/autostart`

Set the boot auto-start mode. This is a Fabricator-level preference, so it can be changed while
the server is running and does not touch `server.properties`.

**Body:** `{ "mode": "always" | "never" | "last" }`

**Response (200):** `{ "success": true, "autoStart": "always", "server": { ... } }`

#### `DELETE /api/servers/<server_id>`

Stops the process, removes scheduled backups and backup records, deletes the server record, then
deletes the install directory from disk.

**Response (200):** `{ "success": true, "message": "Server deleted successfully" }`
**Response (500):** the record is gone but the files could not be removed — the body carries
`error` and `success: false`.

#### `POST /api/servers/<server_id>/install`

Starts the install asynchronously. Java guards run synchronously and fail fast; on success the
download/subprocess work happens in a background thread.

**Response (202):** the current progress entry, e.g. `{ "active": true, "phase": "starting", ... }`

**Errors:**
- `400` no loader/version configured, unsupported loader, or a Java guard failed. Java failures
  include `required_java`, `detected_java`, `java_missing`, `java_too_old`, `compatibility` and
  `recommended_install`.
- `409 {"error": "Another operation is in progress for this server"}`

#### `GET /api/servers/<server_id>/install/progress`

Poll install progress. `active` is `true` until `phase` becomes `done` or `failed`. A missing entry
also reports `active: false`, which is what you see if the backend restarted mid-install. The
frontend polls at roughly 750 ms intervals. Returns `404` for an unknown server.

```json
{
  "active": true,
  "phase": "downloading_server_jar",
  "bytes_done": 12058624,
  "bytes_total": 48234496,
  "server_id": "srv_a1b2c3d4",
  "loader": "fabric"
}
```

**Phase vocabulary** (set by the concrete loaders; treat as opaque strings elsewhere):

| Phase | Meaning |
|---|---|
| `starting` | worker thread spawned |
| `resolving_versions` | versions API call in flight |
| `downloading_installer` | installer JAR download (carries `bytes_done`/`bytes_total`) |
| `downloading_server_jar` | server JAR download (carries `bytes_done`/`bytes_total`) |
| `verifying` | SHA1 check |
| `running_installer` | subprocess execution; phase only, no bytes |
| `detecting_artifacts` | post-install file detection |
| `writing_eula` | final `eula.txt` write |
| `done` | completed successfully |
| `failed` | failed; the entry carries `error` |

#### `POST /api/servers/<server_id>/start`

**Response (200):** `{ "success": true, "message": "...", "server": { ... }, "compatibility": { ... } }`

**Errors:**
- `400` server still `pending` (install first), currently `installing`, or a Java check failed —
  the body carries `java_missing`, `java_too_old`, `required_java`, `detected_java` and
  `recommended_install`.
- `409` a stop is still draining.

#### `POST /api/servers/<server_id>/stop`

Always returns `200`. If the server is running the status flips to `stopping` and the actual stop
runs in a background thread; poll the server record for the final state.

#### `POST /api/servers/<server_id>/restart`

**Response (200):** `{ "success": true, "message": "...", "details": { ... }, "server": { ... } }`
**Error (400):** restart could not complete; `success` is `false`.

#### `GET /api/servers/<server_id>/logs`

**Query:** `limit` (int, default `200`) — applied to each stream separately.

```json
{
  "stdout": [{ "ts": "2026-01-04T12:00:00Z", "text": "Done (7.481s)! For help, type \"help\"" }],
  "stderr": [],
  "running": true
}
```

When no process is registered for the server, the response is
`{ "stdout": [], "stderr": [], "running": false, "message": "Server is not running" }`. This route
does not validate the server id, so an unknown id yields that same not-running body rather than a
`404`.

---

## Server files

All paths are resolved relative to the server's install directory and are rejected if they escape it.

#### `GET /api/servers/<server_id>/files`

**Query:** `path` (string, optional) — relative subdirectory; omit for the install root.

```json
{
  "currentPath": "config",
  "absolutePath": "/srv/servers/srv_a1b2c3d4/config",
  "entries": [
    {
      "name": "fabric",
      "size": 40960,
      "updatedAt": "2026-01-04T12:00:00Z",
      "path": "/srv/servers/srv_a1b2c3d4/config/fabric",
      "relativePath": "config/fabric",
      "isDir": true
    }
  ]
}
```

Directories are listed first, then files, both alphabetically. Directory sizes are the recursive
sum of their contents.

**Errors:** `400` invalid path · `404` directory not found

#### `GET /api/servers/<server_id>/files/content`

**Query:** `path` (string, **required**)

**Response (200):** `{ "path": "server.properties", "content": "..." }`
**Errors:** `400` path missing/invalid, or the file is not UTF-8 text · `404` file not found

#### `PUT /api/servers/<server_id>/files/content`

**Body:** `{ "path": "server.properties", "content": "..." }`

**Response (200):** `{ "success": true }`
**Errors:** `400` path/content missing or invalid · `404` file not found · `500` write failed

---

## Mods

#### `GET /api/servers/<server_id>/mods`

List installed mod files, sorted by name. Same entry shape as the file browser.

#### `DELETE /api/servers/<server_id>/mods/<filename>`

**Response (200):** `{ "success": true, "message": "sodium.jar removed" }`
**Errors:** `400` invalid path · `404` mod file not found

#### `DELETE /api/servers/<server_id>/mods`

Bulk delete. **Body:** `{ "filenames": ["a.jar", "b.jar"] }`

**Response (200):** `{ "success": true, "deleted": ["a.jar"], "errors": [{ "filename": "b.jar", "error": "File not found" }] }`
**Error (400):** `filenames` missing or empty

---

## Console & metrics

#### `POST /api/servers/<server_id>/console`

Send a command to the running server's stdin.

**Body:** `{ "command": "say hello" }`

**Response (200):** the registry result (`success: true`). **Error (400):** command missing, or the
registry rejected it (e.g. the server is not running).

#### `GET /api/servers/<server_id>/metrics`

```json
{ "status": "running", "ram": 2147483648, "pid": 12345 }
```

#### `GET /api/metrics/system`

```json
{
  "cpu": { "percent": 12.4 },
  "memory": { "percent": 48.2, "totalBytes": 16777216000, "usedBytes": 8087896064 }
}
```

**Error (500):** `psutil` is not installed.

---

## Loader versions

Lists the Minecraft and loader versions a registered loader can install. The frontend
(`ServerCreateModal`) uses these as soon as a loader is picked. Loaders registered in
`LOADER_REGISTRY` are exposed here automatically. Lookup is case-insensitive.
Registered today: `fabric`, `forge`, `neoforge`, `quilt`, `vanilla`.

#### `GET /api/loaders/<loader>/versions/game`

Supported Minecraft versions, in a normalized schema:

```json
[
  { "version": "1.21.4", "stable": true,  "type": "release"  },
  { "version": "24w45a", "stable": false, "type": "snapshot" }
]
```

`stable` is the only field every consumer can rely on. `type` is loader-native (e.g.
`release`/`snapshot` for Vanilla) and may be absent when a loader makes no such distinction.

**Error (404):** `{ "error": "Unknown loader: <name>" }`

#### `GET /api/loaders/<loader>/versions/loader`

Loader-specific versions. Loaders without a separate loader version (e.g. Vanilla) return `[]`.

**Query:** `mc_version` (string, optional) — filter to one Minecraft version.

**Response (200):** a loader-native array; the shape varies per loader and the frontend passes it
through opaquely.

Fabric example:
```json
[{ "loader": { "version": "0.16.0", "stable": true } }]
```

---

## Java management

Fabricator can download and manage its own Temurin runtimes alongside whatever Java is on `PATH`.
Set `FABRICATOR_SKIP_JAVA_CHECK=1` to bypass enforcement.

#### `GET /api/java/status`

**Query:** `mc_version` (string, optional) · `required_java` (int, optional) ·
`java_path` (string, optional, default `java`)

```json
{
  "required_java": 21,
  "install_major": 21,
  "system_java": { "path": "java", "version": 17, "meets_requirement": false },
  "managed_java": { "path": "/home/u/.fabricator/java/21", "installed": true, "major": 21, "substituted": false },
  "asset": {
    "download_url": "https://api.adoptium.net/v3/binary/...",
    "filename": "OpenJDK21U-jre_x64_linux_hotspot.tar.gz",
    "size_bytes": 44000000,
    "checksum_algorithm": "sha256",
    "install_major": 21,
    "substituted": false
  },
  "asset_error": null,
  "arch": "x64",
  "compatibility": { "required_java": 21, "enforceable": true },
  "recommended_install": { "required_java": 21, "download_url": "...", "linux_install_command": "sudo apt install openjdk-21-jre-headless", "installer_type": "tar.gz", "arch": "x64" }
}
```

The flat legacy fields (`installed`, `version`, `detected_major`, `java_path`, `meets_requirement`,
`java_enforcement_skipped`, `platform`, `download_url`, `linux_install_command`) are still present
for backward compatibility.

#### `POST /api/java/install`

Start a managed Java install.

**Body:** `{ "major": 21 }`

**Response (200):** `{ "task_id": "...", "status": "queued", "requested_major": 21, "install_major": 21, "substituted": false }`
**Error (400):** `major` is not an integer, or is outside 8–99.

#### `GET /api/java/install/progress/<task_id>`

Poll an install task. **Error (404):** unknown task id.

#### `DELETE /api/java/install/<task_id>`

Signal cancellation. Best-effort: the worker only notices between phases or download chunks.

**Response (200):** the updated task
**Errors:** `404` unknown task · `409` task already in a terminal state

#### `GET /api/java/installed`

```json
{
  "managed": [{ "major": 21, "path": "/home/u/.fabricator/java/21/bin/java", "version": 21 }],
  "system": { "path": "java", "version": 17, "installed": true }
}
```

Managed entries are sorted by `major` ascending and are removable; `major` is the directory name and
`version` is the major actually reported by the binary (`null` if the probe fails). The system entry
is informational only — it lives outside Fabricator's data directory.

#### `DELETE /api/java/installed/<major>`

Remove a managed runtime. Safe: if a server later needs it, the normal resolution flow prompts to
reinstall.

**Response (200):** `{ "success": true, "major": 21 }`
**Errors:** `400` invalid major · `404` no managed install for that major

---

## Players

Player names must match `[A-Za-z0-9_]{1,16}`. Ban/kick reasons must be a single line of ≤ 256
characters. When the server is running, changes are applied through console commands; when it is
stopped, the JSON files are edited directly.

Shared error responses: `409` when the operation needs a different server state ·
`404` when the player is not in the list or is unknown to Mojang · `502` when the Mojang lookup fails.

#### `GET /api/servers/<server_id>/players/state`

`whitelist`, `ops`, `bans`, `ipBans` and `knownPlayers` are passed through verbatim from the
server's `whitelist.json`, `ops.json`, `banned-players.json`, `banned-ips.json` and `usercache.json`
— so their entries carry whatever vanilla writes, not a Fabricator-defined schema. A missing file
reads as `[]`.

```json
{
  "whitelist": [{ "uuid": "...", "name": "Steve" }],
  "ops": [{ "uuid": "...", "name": "Steve", "level": 4, "bypassesPlayerLimit": false }],
  "bans": [],
  "ipBans": [],
  "knownPlayers": [],
  "whitelistActive": false,
  "enforceWhitelist": false,
  "onlineMode": true
}
```

#### `GET /api/servers/<server_id>/players/online`

Currently connected players, tracked from the server's stdout. Returns `[]` when the server is not
running.

```json
[{ "name": "Steve", "uuid": "853c80ef-3c37-49fd-aa49-938b674adae6", "joinedAt": "2026-01-04T12:00:00+00:00" }]
```

`uuid` is backfilled from the local Mojang cache when available and is `null` otherwise — this
endpoint makes no network calls.

#### `POST` / `DELETE /api/servers/<server_id>/players/whitelist`

Add or remove a whitelist entry. **Body:** `{ "name": "Steve" }`

#### `PATCH /api/servers/<server_id>/players/whitelist/active`

Toggle the whitelist at runtime. **Body:** `{ "active": true }`

#### `PATCH /api/servers/<server_id>/players/whitelist/enforce`

Persist the `enforce-whitelist` property. Only while stopped — returns `409` when running (use
`whitelist/active` instead). **Body:** `{ "active": true }`

**Response (200):** `{ "enforceWhitelist": true }`

#### `POST /api/servers/<server_id>/players/ops`

**Body:** `{ "name": "Steve", "level": 4 }` (`level` 1–4, default `4`)

Vanilla's `op` command takes no level argument, so a running server returns `409` for any level
other than `4`.

#### `PATCH /api/servers/<server_id>/players/ops`

Change an op level. **Body:** `{ "name": "Steve", "level": 2 }`

Minecraft only reads `ops.json` at startup, so this returns `409` while the server is running.

#### `DELETE /api/servers/<server_id>/players/ops`

**Body:** `{ "name": "Steve" }`

#### `POST` / `DELETE /api/servers/<server_id>/players/bans`

**Body:** `{ "name": "Steve", "reason": "griefing" }` (`reason` optional; ignored on `DELETE`)

#### `POST` / `DELETE /api/servers/<server_id>/players/bans/ip`

**Body:** `{ "ip": "192.168.1.10", "reason": "..." }`

IPv4 or a wildcard such as `192.168.*`. Invalid values return `400`.

#### `POST /api/servers/<server_id>/players/kick`

Running server only. **Body:** `{ "name": "Steve", "reason": "..." }`

---

## Backups & snapshots

Backup work runs asynchronously: the endpoints return a `job_id` you poll via
`GET /api/backup-jobs/<job_id>`.

### Configs

#### `GET /api/servers/<server_id>/backup-configs`

Each config is annotated with `nextRunTime` pulled live from the scheduler.

#### `POST /api/servers/<server_id>/backup-configs`

**Body** (`name` is required; everything else has a default):
```json
{
  "name": "Nightly",
  "storagePath": "",
  "maxSnapshots": 0,
  "flush": true,
  "shutdown": false,
  "compress": true,
  "exclusions": [],
  "schedule": {
    "enabled": true,
    "frequencyHours": 24,
    "timeOfDay": "03:00",
    "timezone": "Europe/Berlin"
  }
}
```

An empty `storagePath` defaults to `<install>/backups`. `maxSnapshots: 0` means unlimited. An empty
`timezone` falls back to the host zone; a non-empty one must be a valid IANA zone.

**Response (201):** the stored config, with defaults filled in and `nextRunTime` annotated.

```json
{
  "id": "bkc_dc4cb89bbf",
  "serverId": "srv_4f16a5d0",
  "name": "Nightly",
  "storagePath": "",
  "maxSnapshots": 0,
  "flush": true,
  "shutdown": false,
  "compress": true,
  "exclusions": [],
  "schedule": { "enabled": false, "frequencyHours": 24, "timeOfDay": "03:00", "timezone": "" },
  "nextRunTime": null,
  "createdAt": "2026-07-17T09:59:23.953048Z",
  "updatedAt": "2026-07-17T09:59:23.953048Z"
}
```

**Error (400):** missing `name` (`Field 'name' is required`), non-integer or negative
`maxSnapshots`, `frequencyHours <= 0`, or an invalid timezone

#### `PUT /api/servers/<server_id>/backup-configs/<config_id>`

Partial update — the same validation applies to whichever fields are present. `404` if unknown.

#### `DELETE /api/servers/<server_id>/backup-configs/<config_id>`

**Query:** `purge` (bool, optional) — when set, deletes archive files that are both inside the
config's effective storage path and recorded as snapshots of this config.

```json
{
  "success": true,
  "config_id": "bkc_dc4cb89bbf",
  "purge": true,
  "deleted_files": 3,
  "deleted_paths": ["..."],
  "retained_files": 1,
  "retained_paths": ["..."]
}
```

The response always reports both lists — no silent orphans. Without `purge`, the files stay on disk
and all appear under `retained_paths`.

### Snapshots

#### `GET /api/servers/<server_id>/snapshots`

#### `DELETE /api/servers/<server_id>/snapshots/<snapshot_id>`

Unlinks the archive and removes the record. **Errors:** `404` unknown snapshot · `500` unlink failed

#### `GET /api/servers/<server_id>/snapshots/<snapshot_id>/download`

**Query:** `format` (`tar` default, or `zip`)

`zip` repacks the archive on the fly into a flat directory tree for browsers; the temp file is
cleaned up after the response.

**Errors:** `404` unknown snapshot, or the archive is missing on disk

#### `POST /api/servers/<server_id>/snapshots/<snapshot_id>/restore`

**Body:** `{ "mode": "in_place" | "reset" }`

**Response (202):** `{ "success": true, "job_id": "..." }`
**Errors:** `400` invalid mode · `404` unknown snapshot

### Running backups

#### `POST /api/servers/<server_id>/backup-configs/<config_id>/run`

Run a configured backup now. **Response (202):** `{ "success": true, "job_id": "..." }`

#### `POST /api/servers/<server_id>/backup-quick`

Ad-hoc backup without a stored config.

**Body:** `{ "storagePath": null, "compress": true, "flush": true, "shutdown": false }` (all optional)

**Response (202):** `{ "success": true, "job_id": "..." }`

#### `GET /api/servers/<server_id>/backup-summary`

```json
{
  "total_snapshots": 12,
  "total_size_bytes": 4823449600,
  "last_snapshot": { "id": "...", "createdAt": "..." },
  "next_run": { "config_id": "bkc_dc4cb89bbf", "config_name": "Nightly", "next_run_time": "..." },
  "configs_count": 2,
  "defaultStoragePath": "/srv/servers/srv_a1b2c3d4/backups"
}
```

#### `POST /api/servers/<server_id>/world-import`

Upload a world archive and replace the server's active world. The raw archive bytes are the request
body (`fetch(url, { body: file })`); the display name comes from the `filename` query parameter or
the `X-Filename` header.

**Response (202):** `{ "success": true, "job_id": "..." }`
**Errors:** `400` empty upload or invalid archive · `413` upload exceeds the limit
(`FABRICATOR_MAX_WORLD_UPLOAD_BYTES`)

#### `GET /api/backup-jobs/<job_id>`

Poll any backup, restore or world-import job. Job ids are globally unique, so this route is not
server-scoped.

**Response (200):** `{ "active": true, ... }` · **Error (404):** unknown job

---

## Modrinth integration

#### `GET /api/modrinth/search`

**Query:** `query` (string) · `mc_version` (string, optional) · `loader` (string, optional) ·
`limit` (int, default `20`) · `offset` (int, default `0`) ·
`index` (`downloads` default, `relevance`, `follows`, `newest`, `updated`)

```bash
GET /api/modrinth/search?query=sodium&mc_version=1.20.1&loader=fabric&limit=10
```

```json
{
  "hits": [
    {
      "project_id": "AANobbMI",
      "slug": "sodium",
      "title": "Sodium",
      "description": "A modern rendering engine...",
      "downloads": 90301924,
      "icon_url": "https://cdn.modrinth.com/...",
      "project_type": "mod",
      "versions": ["1.20.1", "1.20.2"],
      "client_side": "required",
      "server_side": "optional"
    }
  ],
  "offset": 0,
  "limit": 10,
  "total_hits": 1
}
```

#### `GET /api/modrinth/modpacks/search`

Same parameters and response shape as `/search`, restricted to modpacks.

#### `GET /api/modrinth/project/<project_id>`

Project details. `GET /api/modrinth/mod/<mod_id>` is a legacy alias with identical behaviour.

```json
{
  "id": "AANobbMI",
  "slug": "sodium",
  "title": "Sodium",
  "description": "The fastest and most compatible...",
  "downloads": 90301924,
  "categories": ["optimization", "fabric"],
  "client_side": "required",
  "server_side": "optional",
  "versions": ["versionId1", "versionId2"],
  "game_versions": ["1.20.1", "1.20.2"],
  "loaders": ["fabric"]
}
```

#### `GET /api/modrinth/project/<project_id>/versions`

All versions of a project. `GET /api/modrinth/mod/<mod_id>/versions` is a legacy alias.

**Query:** `loaders` (repeatable) · `game_versions` (repeatable) · `featured` (bool, optional)

```bash
GET /api/modrinth/project/sodium/versions?loaders=fabric&game_versions=1.20.1
```

```json
[
  {
    "id": "versionId",
    "version_number": "0.5.13",
    "name": "Sodium 0.5.13 for Fabric",
    "version_type": "release",
    "date_published": "2025-03-03T17:45:49.132919Z",
    "downloads": 12345,
    "game_versions": ["1.20.1"],
    "loaders": ["fabric"],
    "files": [
      {
        "url": "https://cdn.modrinth.com/.../sodium-fabric-0.5.13+mc1.20.1.jar",
        "filename": "sodium-fabric-0.5.13+mc1.20.1.jar",
        "primary": true,
        "size": 1234567,
        "hashes": { "sha512": "...", "sha1": "..." }
      }
    ]
  }
]
```

#### `GET /api/modrinth/project/<project_id>/resolve-version`

Resolve the best version for a target.

**Query:** `mc_version` (string, **required**) · `loader` (string, optional)

```json
{
  "project_id": "sodium",
  "mc_version": "1.20.1",
  "loader": "fabric",
  "version": { "id": "...", "version_number": "0.5.13", "files": ["..."] },
  "download_url": "https://cdn.modrinth.com/..."
}
```

`version` is the complete Modrinth version object (the same shape `/versions` returns), not a
summary. `loader` echoes back whatever you sent, including `null`.

**Errors:** `400` `mc_version` missing · `404` no suitable version found

#### `GET /api/modrinth/version/<version_id>`

A single Modrinth version by id.

#### `GET /api/modrinth/mod/<mod_id>/download-url`

Direct download URL for the best matching version.

**Query:** `mc_version` (string, **required**) · `loader` (string, optional, default `fabric`)

```json
{ "download_url": "https://cdn.modrinth.com/data/AANobbMI/versions/OihdIimA/sodium-fabric-0.5.13%2Bmc1.20.1.jar" }
```

**Errors:** `400` `mc_version` missing · `404` no suitable version found

#### `POST /api/modrinth/mod/<mod_id>/install`

Download a mod and install it into the server's mods folder. The download is hash-verified.

**Body:** `mc_version` (string, **required**) · `server_id` (string, **required**) ·
`loader` (string, optional, default `fabric`)

```json
{ "mc_version": "1.20.1", "server_id": "srv_a1b2c3d4", "loader": "fabric" }
```

**Response (200):**
```json
{
  "success": true,
  "message": "Mod installed successfully",
  "file": "sodium-fabric-0.5.13+mc1.20.1.jar",
  "path": "/srv/servers/srv_a1b2c3d4/mods/sodium-fabric-0.5.13+mc1.20.1.jar"
}
```

**Errors:** `400` `server_id` or `mc_version` missing, or a `mods_folder` override was sent (no
longer allowed) · `404` server not found, or no suitable version · `409` another operation holds
the server lock

#### `POST /api/modrinth/modpack/<project_id>/install`

Install a modpack into a server. The server must be stopped.

**Body:** `server_id` (string, **required**) · `mc_version` (string, optional) ·
`loader` (string, optional) · `clean_install` (bool, default `true`) ·
`create_backup` (bool, default `true`) · `allow_missing` (bool, default `false`) ·
`mod_side_overrides` (object, optional)

**Response (200):** the install result plus `success`, `message`, `backup_file` (when a backup was
made) and `java_warning` (when the pack's Minecraft version needs a newer Java than the one detected).

**Errors:** `400` server running, or install path unresolvable · `404` server not found ·
`409` an install is already in progress · `500` backup or install failure

#### `GET /api/modrinth/modpack/install-progress/<server_id>`

**Response (200):** `{ "active": true, "stage": "downloading", "current": 12, "total": 80, "detail": "..." }`
or `{ "active": false }` when nothing is running.

#### `GET /api/modrinth/categories`

```json
[{ "icon": "...", "name": "adventure", "project_type": "mod", "header": "Adventure" }]
```

#### `GET /api/modrinth/loaders`

```json
[{ "icon": "...", "name": "fabric", "supported_project_types": ["mod", "modpack"] }]
```

#### `GET /api/modrinth/game-versions`

```json
[{ "version": "1.20.1", "version_type": "release", "date": "2023-06-12T00:00:00Z", "major": true }]
```

Upstream Modrinth failures are surfaced with the upstream status code (or `502` when there is none).

---

## playit.gg tunnel

Exposes a server publicly through a playit.gg tunnel. Not supported on Windows — every endpoint
then reports `status: "unsupported"`.

#### `GET /api/playit/status`

```json
{
  "status": "running",
  "claim_url": null,
  "error_reason": null,
  "binary_verified": true,
  "tunnels": [
    {
      "local_port": 25565,
      "address": "example.gl.at.ply.gg:12345",
      "disabled_reason": null,
      "name": "my-tunnel",
      "tunnel_type": "minecraft-java"
    }
  ],
  "tunnels_known": true
}
```

`status` is daemon/account level and is one of `unsupported`, `stopped`, `claiming`, `starting`,
`running`, `error`. `error` means a real account/daemon failure — a per-tunnel `disabled_reason` is
not a global error and rides on the tunnel instead.

Derive a server's public address by matching `tunnel.local_port` to that server's port; `address`
may be `null`. "No matching tunnel" is a per-server hint, not an error. `tunnels_known` stays
`false` until the first successful poll, so callers can tell "zero tunnels" apart from "not
reachable yet"; both leave `tunnels` empty.

#### `POST /api/playit/start` · `POST /api/playit/stop` · `POST /api/playit/reset`

Each performs the action and returns the full post-action status, so no follow-up poll is needed.

---

## System updates

#### `GET /api/system/update/status`

Current updater state plus the latest-version check. `selfUpdateDisabled` is `true` when the
deployment manages updates out-of-band (the container image sets `FABRICATOR_DISABLE_SELF_UPDATE=1`).

#### `POST /api/system/update`

Start an asynchronous self-update.

**Body:** `{ "version": "1.2.3" }` — optional; a release tag or `latest`.

**Response (202):** `{ "started": true, "requestedVersion": "1.2.3" }`

**Errors:**
- `403` self-update is disabled for this deployment (`FABRICATOR_DISABLE_SELF_UPDATE=1`).
- `409` the update did not start. The route maps **every** unstarted outcome to `409`, so this
  covers an update already in progress, an invalid version string, and a failure to queue the
  request — read `error` in the body to tell them apart. Note that an invalid version yields `409`
  here, not `400`.

---

## Configuration

### Environment variables

Set these in `.env` or the environment.

```bash
# Flask
FLASK_ENV=development            # or 'production'
HOST=127.0.0.1                   # loopback by default; set explicitly for remote access
PORT=5000
SECRET_KEY=...                   # session signing key; auto-generated and persisted if unset

# CORS — comma-separated allowlist. '*' is rejected; entries need an http(s) scheme and a host.
CORS_ORIGINS=http://localhost:3000

# Storage (defaults: %APPDATA%\Fabricator on Windows, ~/.fabricator on POSIX;
# /var/lib/fabricator/... under FLASK_ENV=production)
SERVER_ROOT=...                  # server install directories
SERVER_INDEX_FILE=...            # servers.json
JAVA_ROOT=...                    # managed Java runtimes
BACKUPS_DIR=...                  # backup archives
FABRICATOR_APPDATA=...           # override the whole data directory

# Authentication
FABRICATOR_DISABLE_AUTH=1        # turn off the built-in login entirely
FABRICATOR_AUTH_PASSWORD_HASH=... # declare the password out-of-band (blocks /change-password)
FABRICATOR_SESSION_COOKIE_SECURE=1

# Server process
SERVER_COMMAND="java -Xmx4G -jar server.jar nogui"   # fallback launch command

# Behaviour toggles
FABRICATOR_SKIP_JAVA_CHECK=1     # bypass Java version enforcement (dev/testing only)
FABRICATOR_DISABLE_SCHEDULER=1   # do not boot the backup scheduler
FABRICATOR_DISABLE_SELF_UPDATE=1 # make POST /api/system/update return 403
FABRICATOR_MAX_WORLD_UPLOAD_BYTES=...  # world-import cap; default 10 GiB

# Self-updater
FABRICATOR_REPO=philderks/Fabricator
FABRICATOR_UPDATE_MODE=...
FABRICATOR_UPDATE_DIR=/var/lib/fabricator/update

# playit.gg
PLAYIT_ENABLED=true              # must be the literal 'true' (see below)
PLAYIT_RUNTIME_DIR=...           # writable dir for the agent's secret; often needs setting
PLAYIT_BINARY_VERIFIED=true      # must be the literal 'true'
```

**Truthiness is not uniform.** Most flags (`FABRICATOR_DISABLE_AUTH`, `FABRICATOR_SKIP_JAVA_CHECK`,
`FABRICATOR_SESSION_COOKIE_SECURE`) go through `bool_from_str`, which accepts `1`, `true`, `yes` or
`on`, case-insensitively. But `FABRICATOR_DISABLE_SCHEDULER` and `FABRICATOR_DISABLE_SELF_UPDATE`
match the literal string `1` only, and `PLAYIT_ENABLED` / `PLAYIT_BINARY_VERIFIED` match the literal
lowercase `true` only — `PLAYIT_ENABLED=1` does **not** work.

`PLAYIT_ENABLED` is only a fallback: the state file written by the dashboard toggle wins when present.

`SECRET_KEY` and `FABRICATOR_AUTH_PASSWORD_HASH` are sensitive — never log them.

### Configuration classes

In `backend/core/config.py`. `get_config()` builds a fresh instance per call, so environment
overrides always take effect (no import-time snapshotting).

- `DevelopmentConfig` — debug on; data under the user's appdata directory.
- `ProductionConfig` — debug off; data under `/var/lib/fabricator`.

---

## Loader registry (developers)

The loader dispatch layer lives in `backend/server/installer/__init__.py`. Adding a loader takes
three steps:

1. **Subclass `InstallerBase`** (`backend/server/installer/base.py`) and implement:
   - `loader_name` (property) — the registry key, e.g. `"neoforge"`
   - `get_minecraft_versions()` → `List[{version, stable, type?}]` in the normalized schema (see
     `/api/loaders/<loader>/versions/game`)
   - `get_available_versions(mc_version)` → loader-native array; `[]` when the loader has no
     separate loader version
   - `install(mc_version, loader_version=None)` → `InstallResult` with `launch: LaunchSpec` set. The
     `LaunchSpec` is persisted in `servers.json` and drives `ServerProcessRegistry._build_command`

2. **Register it in `LOADER_REGISTRY`:**
   ```python
   from .neoforge import NeoForgeInstaller

   LOADER_REGISTRY: Dict[str, Type[InstallerBase]] = {
       "fabric": FabricInstaller,
       "vanilla": VanillaInstaller,
       "neoforge": NeoForgeInstaller,
       "quilt": QuiltInstaller,
       "forge": ForgeInstaller,
   }
   ```

   `get_installer_for(loader, install_path)` (case-insensitive) and `supported_loaders()` pick up
   the new entry automatically — routes and the install flow need no changes.

3. **Frontend:** add an option to `loaderOptions` in
   `frontend/src/components/modals/ServerCreateModal.vue` using the same `value` as `loader_name`.

If your installer needs Java at install time (not just at runtime), set
`requires_java_for_install` so the install route runs the extra Java guard.
`_build_command` raises `ValueError` on an unknown `LaunchSpec.type` — that is deliberate, so a
record written by a newer build is caught early on an older one.

---

## Modrinth client (Python)

`ModrinthClient` can be used directly:

```python
from pathlib import Path
from backend.modrinth.client import ModrinthClient

client = ModrinthClient()

results = client.search(project_type="mod", query="sodium", mc_version="1.20.1", loader="fabric")
resolved = client.get_project_download_url(project_id="sodium", mc_version="1.20.1", loader="fabric")
file = client.download_mod(resolved["url"], Path("./mods"), hashes=resolved["hashes"])
```

Key methods:

- `search(project_type, query, mc_version, loader, limit, offset, index)` — search projects
- `get_project(project_id)` — project details
- `get_project_versions(project_id, loaders, game_versions, featured)` — versions
- `get_version(version_id)` — a single version
- `resolve_project_version(project_id, mc_version, loader)` — best matching version + URL
- `get_project_download_url(project_id, mc_version, loader)` — resolve straight to a URL + hashes
- `download_mod(url, target_folder, hashes=...)` — hash-verified download
- `install_modpack(project_id, install_path, ...)` — full modpack install

Failures raise `ModrinthApiError`, which carries the upstream `status_code` and any `details`.

---

## Worked examples

Authentication is on unless you set `FABRICATOR_DISABLE_AUTH=1`, so log in first and reuse the
session cookie. The default base URL is `http://localhost:5000`.

```bash
# Log in and store the session cookie
curl -c cookies.txt -X POST http://localhost:5000/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"password": "your-password"}'
```

### Create, install and start a server

```bash
# 1. Create the record (returns 201 with the new id, e.g. srv_a1b2c3d4)
curl -b cookies.txt -X POST http://localhost:5000/api/servers \
  -H 'Content-Type: application/json' \
  -d '{"name": "Survival", "version": "1.20.1", "loader": "fabric",
       "port": 25565, "installPath": "/var/lib/fabricator/servers/survival"}'

# 2. Lay down the files (returns 202 — the work runs in the background)
curl -b cookies.txt -X POST http://localhost:5000/api/servers/srv_a1b2c3d4/install

# 3. Poll until "active": false
curl -b cookies.txt http://localhost:5000/api/servers/srv_a1b2c3d4/install/progress

# 4. Start it
curl -b cookies.txt -X POST http://localhost:5000/api/servers/srv_a1b2c3d4/start
```

### Find and install a mod

```bash
curl -b cookies.txt "http://localhost:5000/api/modrinth/search?query=create&mc_version=1.20.1&loader=fabric"

# server_id is required — the mods folder is resolved from it
curl -b cookies.txt -X POST http://localhost:5000/api/modrinth/mod/create-fabric/install \
  -H 'Content-Type: application/json' \
  -d '{"mc_version": "1.20.1", "loader": "fabric", "server_id": "srv_a1b2c3d4"}'
```

### Back up a server

```bash
# Ad-hoc backup, no stored config needed (returns 202 + job_id)
curl -b cookies.txt -X POST http://localhost:5000/api/servers/srv_a1b2c3d4/backup-quick \
  -H 'Content-Type: application/json' -d '{"compress": true, "flush": true}'

# Poll the job
curl -b cookies.txt http://localhost:5000/api/backup-jobs/<job_id>
```

### Inspect a running server

```bash
curl -b cookies.txt http://localhost:5000/api/servers/srv_a1b2c3d4/metrics
curl -b cookies.txt "http://localhost:5000/api/servers/srv_a1b2c3d4/logs?limit=50"
curl -b cookies.txt -X POST http://localhost:5000/api/servers/srv_a1b2c3d4/console \
  -H 'Content-Type: application/json' -d '{"command": "say hello"}'
```

---

## Testing

```bash
pytest
```

---

## Security notes

- **Authentication**: single-operator password login, enabled by default; disable with
  `FABRICATOR_DISABLE_AUTH=1`. The `/api/` gate is default-deny.
- **CORS**: explicit allowlist only — `*` is rejected at startup.
- **Path traversal**: file, mod and backup paths are resolved and rejected if they escape the
  server's install directory.
- **Self-update**: gate it with `FABRICATOR_DISABLE_SELF_UPDATE=1` when the panel is exposed and
  updates come from elsewhere.
- **Modrinth rate limits**: the client sets an identifying `User-Agent` as Modrinth's policy
  requires, but it does **not** throttle, back off, or retry. Requests go out as fast as callers
  make them, and a `429` from Modrinth is surfaced to you unchanged (`ModrinthApiError` →
  HTTP `429`) rather than being retried. Modrinth's documented limit is 300 requests/minute; staying
  under it is the caller's responsibility.
- **Outbound timeouts**: Modrinth calls use a 15-second timeout.

---

## License

[GNU Affero General Public License v3.0](LICENSE) (AGPL-3.0).
Copyright © 2026 Philipp Noél Derks and Linus Sommermeyer.

AGPL-3.0 is a network copyleft licence: if you run a modified Fabricator as a network service, you
must offer its users the corresponding source of your modified version.

## Contributing

Bug reports and pull requests are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md) for the full
process. In short:

- **Bugs** and small self-contained fixes: open an issue; a PR alongside it is fine.
- **New features**, refactors, restructuring, build/CI/packaging changes: open an issue and wait for
  agreement **before** writing code. Unsolicited structural PRs are likely to be declined.
- **Security vulnerabilities**: do not open a public issue or PR — report privately.
- New behavior should come with a test; a bug fix should come with a test that fails before the fix.
  `pytest` is already in `requirements.txt`, so there is no separate dev install.

Opening a pull request means agreeing to the Contributor License Agreement in
[CONTRIBUTING.md](CONTRIBUTING.md): contributions are licensed to the public under AGPL-3.0, and you
also grant the maintainers a perpetual, royalty-free licence to relicense them, including
commercially. The CLA Assistant bot records your acceptance once per GitHub account.

## Support

- GitHub Issues: [Fabricator Issues](https://github.com/philderks/Fabricator/issues)
- Modrinth API docs: [docs.modrinth.com](https://docs.modrinth.com)
