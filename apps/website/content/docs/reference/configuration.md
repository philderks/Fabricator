---
title: Configuration
description: Reference for Fabricator configuration files and environment variables.
---

Fabricator reads environment configuration at runtime. In a packaged native install, systemd loads `/etc/fabricator/fabricator.env` through `EnvironmentFile=`. In Docker, set the same values as `environment:` entries in `docker-compose.yml`; the image pins persistent paths onto `/data`.

## Main config file

Default native production file created by the installer:

```ini
# Fabricator environment configuration
HOST=0.0.0.0
PORT=5000
FLASK_ENV=production
SERVER_ROOT=/var/lib/fabricator/servers
SERVER_INDEX_FILE=/var/lib/fabricator/servers.json
PLAYIT_ENABLED=false
PLAYIT_BINARY_VERIFIED=true
```

Restart after editing:

```bash
sudo systemctl restart fabricator
```

For Docker, recreate the container after compose changes:

```bash
docker compose up -d
```

## Environment variables

| Variable | Default | Description |
| --- | --- | --- |
| `HOST` | development: `127.0.0.1`; native packaged install and Docker: `0.0.0.0` | Bind address for the Flask server. In Docker, keep this at `0.0.0.0` and restrict the host-side port mapping instead. |
| `PORT` | `5000` | HTTP port for the dashboard and API. |
| `FLASK_ENV` | `development`; packaged installs use `production` | Controls production defaults. |
| `SERVER_ROOT` | native production: `/var/lib/fabricator/servers`; Docker: `/data/servers`; development: app data `servers/` | Root directory for managed server instances. |
| `SERVER_INDEX_FILE` | native production: `/var/lib/fabricator/servers.json`; Docker: `/data/servers.json`; development: app data `servers.json` | JSON index of configured servers. |
| `JAVA_ROOT` | native production: `/var/lib/fabricator/java`; Docker: `/data/java`; development: app data `java/` | Directory for managed Java runtimes. |
| `BACKUPS_DIR` | native production: `/var/lib/fabricator/backups`; Docker: `/data/backups`; development: app data `backups/` | Default backup directory. |
| `CORS_ORIGINS` | `http://localhost:3000` | Comma-separated list of allowed browser origins for separate frontends. Wildcard `*` is rejected. |
| `FABRICATOR_MAX_WORLD_UPLOAD_BYTES` | `10737418240` (10 GiB) | Max streamed upload size for **Backups → Import world**. Raise the reverse proxy body limit too if one sits in front. |
| `PLAYIT_ENABLED` | `false` | Starts the shared playit.gg tunnel agent automatically when no dashboard-persisted state file exists. Prefer the dashboard toggle for normal use. |
| `PLAYIT_BINARY_VERIFIED` | installer-managed | Whether the installer/update verified the pinned playit binaries. The UI surfaces a non-blocking warning when false. |
| `PLAYIT_RUNTIME_DIR` | native production: `/var/lib/fabricator/playit`; Docker: `/data/playit`; development: app data `playit/` | Runtime directory for the playit secret, socket, PID file, logs, and enabled-state marker. Usually only changed for development/manual installs. |
| `SECRET_KEY` | generated and persisted in `auth.json` | Optional fixed Flask session signing key. Env value overrides the persisted key. |
| `FABRICATOR_AUTH_PASSWORD_HASH` | unset | Optional env-managed operator password hash. When set, it skips setup mode and cannot be changed from the dashboard. |
| `FABRICATOR_DISABLE_AUTH` | false | Explicitly disables built-in auth. Use only behind a trusted reverse-proxy/VPN auth layer. |
| `FABRICATOR_SESSION_COOKIE_SECURE` | false | Adds the `Secure` flag to the session cookie. Enable when the public dashboard URL is HTTPS. |
| `FABRICATOR_SKIP_JAVA_CHECK` | unset / false | Development escape hatch to bypass Java version enforcement. Do not enable in production. |
| `FABRICATOR_VERSION` | `latest` in installer | Installer target release tag. |
| `FABRICATOR_REPO` | `philderks/Fabricator` | Installer repository override. |
| `FABRICATOR_SKIP_OS_PACKAGES` | `0` | Internal update optimization used by `tools/update.sh`; valid only in update mode. |

## Authentication state

`auth.json` lives next to `servers.json`: `/var/lib/fabricator/auth.json` on native installs and `/data/auth.json` in Docker. It stores the generated session key and hashed operator password when those values are not env-managed. See [Authentication](/getting-started/authentication/) for setup, reset, and disabling guidance.

## CORS allowlist

`CORS_ORIGINS` must contain concrete HTTP(S) origins:

```ini
CORS_ORIGINS=http://localhost:3000,https://dashboard.example.com
```

`CORS_ORIGINS=*` is rejected because Fabricator exposes destructive endpoints such as start/stop, file writes, mod deletes, backups, imports, and uninstall/update workflows.

## World import upload limit

`FABRICATOR_MAX_WORLD_UPLOAD_BYTES` is enforced while the upload stream is written to disk, so an oversize archive is rejected before it lands fully on the host. If nginx, Caddy, Cloudflare, or another proxy sits in front, configure its request body limit as well or it may reject large worlds before Fabricator sees them.

## playit.gg runtime

The native installer creates `/var/lib/fabricator/playit` for the `fabricator` service user and installs pinned `playit`/`playit-cli` binaries into `/usr/local/bin` when the host architecture is supported. Docker stores the same runtime state in `/data/playit`.

The runtime directory stores the account secret, daemon socket, PID file, log file, and dashboard-persisted enabled state. Treat it as sensitive because the saved secret can authenticate the playit agent.

Use the [playit.gg tunnels guide](/guides/playit/) for dashboard setup and tunnel troubleshooting.

## Server root safety

Server install paths are resolved inside `SERVER_ROOT`. Relative install paths are interpreted below the root. Attempts to escape the root are rejected by the backend.

## Per-server settings

Most game options are persisted in Fabricator's server index and written into the instance's `server.properties`. Settings are editable only while the server is stopped. See [Server settings](/guides/server-settings/) for the UI behavior and field groups.
