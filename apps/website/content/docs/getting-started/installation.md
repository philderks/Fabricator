---
title: Installation
description: Install Fabricator with Docker or the native Linux release installer.
---

Fabricator installs either from the published Docker image or from GitHub release tarballs. Docker is the recommended cross-platform path; the native installer is for Linux systemd hosts.

## Docker quick start

```bash
curl -fsSL https://raw.githubusercontent.com/philderks/Fabricator/main/docker-compose.yml -o docker-compose.yml
docker compose up -d
```

The packaged compose file publishes the dashboard to host loopback only (`127.0.0.1:5000`) and stores all state in the `fabricator-data` volume mounted at `/data`.

Open `http://127.0.0.1:5000/` and complete the first-boot password setup. To reach the dashboard from another machine, put a reverse proxy/VPN/firewall in front of the loopback port or deliberately change the compose port mapping. Keep `HOST=0.0.0.0` inside the container; restrict exposure on the host side.

Minecraft server ports are not published by default. Use [playit.gg tunnels](/docs/guides/playit/) or map each server port explicitly, for example `25565:25565`.

For details, see [Docker](/docs/getting-started/docker/).

## Native Linux install

```bash
curl -fsSL https://fabricator.site/install.sh | bash
```

The script requires root privileges. If you run it as a non-root user, it uses `sudo`.

By default this installs the latest published release. After install, open the printed URL, then complete the first-boot password setup.

:::tip[Inspect before running]
If you prefer to inspect the installer first, download it and run it explicitly:

```bash
curl -fsSLO https://fabricator.site/install.sh
less install.sh
bash install.sh
```
:::

## Install a specific version

```bash
curl -fsSL https://fabricator.site/install.sh | FABRICATOR_VERSION=vX.Y.Z bash
```

`FABRICATOR_VERSION=main` is intentionally not supported by the installer. Use a release tag.

## What the native installer does

1. Detects the Linux distro family.
2. Installs host packages such as Python, curl, tar, rsync, CA certificates, grep, and sed.
3. Ensures the `fabricator` system user exists.
4. Downloads pinned `playit` and `playit-cli` binaries for supported Linux architectures and verifies their sha256 checksums.
5. Downloads `fabricator-<tag>.tar.gz` from GitHub Releases.
6. Syncs app files into `/opt/fabricator/app`.
7. Creates or updates `/opt/fabricator/venv` and installs Python requirements.
8. Installs the `fabricator` CLI entry point and symlinks it to `/usr/local/bin/fabricator`.
9. Creates `/etc/fabricator/fabricator.env` if it does not exist.
10. Writes `/etc/systemd/system/fabricator.service`.
11. Grants the service user passwordless sudo for the bundled update wrapper only.
12. Enables and starts `fabricator.service`.

## Update an existing install

Native install:

```bash
curl -fsSL https://fabricator.site/install.sh | bash -s -- --update
```

During update, Fabricator backs up important state under `/var/lib/fabricator/update-backups/<timestamp>/`, including `servers.json` and `fabricator.env` when present.

Docker install:

```bash
docker compose pull && docker compose up -d
```

The Docker image disables dashboard self-update because the container should be updated by pulling a new image.

## Directory layout

| Path | Purpose |
| --- | --- |
| `/opt/fabricator/app` | Application code synced from the release archive. |
| `/opt/fabricator/venv` | Python virtualenv used by the native service and CLI. |
| `/opt/fabricator/app/.fabricator_version` | Installed release marker. |
| `/var/lib/fabricator` | Native mutable data root. |
| `/var/lib/fabricator/servers` | Default native server install root. |
| `/var/lib/fabricator/servers.json` | Native server index. |
| `/var/lib/fabricator/auth.json` | Native auth/session state when not env-managed. |
| `/var/lib/fabricator/java` | Native managed Java runtimes. |
| `/var/lib/fabricator/backups` | Native default backup root. |
| `/var/lib/fabricator/playit` | Native playit.gg runtime directory for the saved secret, socket, PID file, logs, and enabled-state marker. |
| `/data` | Docker persistent volume containing servers, auth, Java runtimes, backups, and playit state. |
| `/usr/local/bin/playit` | Optional playit daemon installed by the native installer when supported and checksum-verified. |
| `/usr/local/bin/playit-cli` | Optional playit CLI used for the headless account claim flow. |
| `/etc/fabricator/fabricator.env` | Native environment configuration loaded by systemd. |
| `/etc/systemd/system/fabricator.service` | Native systemd unit. |
| `/etc/sudoers.d/fabricator-self-update` | Limited sudo rule for dashboard self-update. |

## Service management

```bash
sudo systemctl status fabricator
sudo systemctl restart fabricator
sudo journalctl -u fabricator -f
```

You can also use the CLI on native installs:

```bash
fabricator status
fabricator version
fabricator update
fabricator hash-password
```

## Accessing the dashboard

The native installer writes this packaged config by default:

```ini
HOST=0.0.0.0
PORT=5000
FLASK_ENV=production
SERVER_ROOT=/var/lib/fabricator/servers
SERVER_INDEX_FILE=/var/lib/fabricator/servers.json
```

Open `http://<host-ip>:5000/`, complete [Authentication](/docs/getting-started/authentication/), then place Fabricator behind a reverse proxy before exposing it broadly.

## Uninstall

Use the installed CLI on native installs:

```bash
sudo fabricator uninstall
```

The command asks you to type `yes` and then removes the service, app files, data directory, config directory, service user, and systemd unit. It is destructive.
