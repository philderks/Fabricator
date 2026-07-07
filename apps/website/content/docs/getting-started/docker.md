---
title: Docker
description: Run Fabricator from the published GHCR container image.
---

Docker is the recommended path when you want the smallest host footprint, or when you are running Fabricator on macOS or Windows through Docker Desktop / WSL2. Each release publishes a multi-architecture image to GitHub Container Registry:

```text
ghcr.io/philderks/fabricator:latest
```

The container runs as an unprivileged `fabricator` user and stores all persistent state on one `/data` volume.

## Quick start

Download the compose file from the product repository and start the service:

```bash
curl -fsSL https://raw.githubusercontent.com/philderks/Fabricator/main/docker-compose.yml -o docker-compose.yml
docker compose up -d
```

By default the compose file publishes the dashboard to host loopback only:

```yaml
ports:
  - "127.0.0.1:5000:5000"
```

Open `http://127.0.0.1:5000/` locally, or put a reverse proxy on the same host in front of that loopback port.

## First boot

Authentication is enabled by default. On first boot, if no password has been configured yet, Fabricator redirects to a one-time setup page. Create the operator password there before exposing the dashboard beyond a trusted local connection.

If the dashboard will be reachable before you can complete the setup page, configure the password declaratively instead:

```bash
# Run from a Fabricator source checkout, or inside a temporary container with the app available.
python -m backend.auth hash
```

Then set the generated value as `FABRICATOR_AUTH_PASSWORD_HASH` in `docker-compose.yml`. Pin `SECRET_KEY` too if you want to manage the session signing key explicitly; otherwise Fabricator generates and persists it in `/data/auth.json`.

## Ports and Minecraft servers

The compose file intentionally does **not** publish Minecraft server ports. For each server, either:

- use the built-in [playit.gg tunnel guide](/docs/guides/playit/) to expose Minecraft without router port-forwarding, or
- map the server port explicitly, for example `25565:25565`.

Keep `HOST=0.0.0.0` inside the container. Restrict exposure with the host-side port mapping, firewall, VPN, or reverse proxy instead.

## Persistent data

The image pins runtime paths onto `/data`:

| Path | Purpose |
| --- | --- |
| `/data/servers` | Managed server instances. |
| `/data/servers.json` | Server index. |
| `/data/java` | Managed Java runtimes. |
| `/data/backups` | Backup storage. |
| `/data/playit` | playit.gg secret, socket, logs, and enabled-state marker. |
| `/data/auth.json` | Session signing key and hashed operator password when not env-managed. |

## Updating

Pull the latest image and recreate the container. The named volume keeps server data and configuration:

```bash
docker compose pull && docker compose up -d
```

The Docker image disables Fabricator's in-dashboard self-update. Use image updates for container installs.
