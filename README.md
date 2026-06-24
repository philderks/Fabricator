<div align="center">

<img src="frontend/public/favicon.svg" alt="Fabricator Logo" width="92" height="92" />

# Fabricator

**Self-hosted web dashboard for managing Fabric and Vanilla Minecraft servers.**

[![License: GPL-3.0](https://img.shields.io/badge/license-GPL--3.0-blue?style=flat-square)](LICENSE)
[![Stars](https://img.shields.io/github/stars/philderks/Fabricator?style=flat-square)](https://github.com/philderks/Fabricator/stargazers)
[![Platform](https://img.shields.io/badge/platform-Linux%20%7C%20Windows%20%7C%20Docker-lightgrey?style=flat-square)](https://github.com/philderks/Fabricator)

[Website](https://fabricator.site/) | [Documentation](https://docs.fabricator.site/)

</div>

---

<div align="center">
  <img width="2560" height="1282" alt="image" src="https://github.com/user-attachments/assets/78f797c8-f1ac-4e33-87c9-a3d79b207c4a" />
</div>


---

## Features

| | Feature | Status |
|---|---|---|
| 🧩 | **Loaders** — Fabric (modded) and Vanilla | ✅ Available |
| 📦 | **Mod Management** — install, remove, and browse Fabric mods | ✅ Available |
| 📋 | **Logs & Monitoring** — live log stream, TPS and RAM graphs | ✅ Available |
| 💾 | **Backups & Restore** — manual snapshots, restore from any backup | ✅ Available |
| 🌍 | **World Import** — upload a world archive and swap it in | ✅ Available |
| 🖥️ | **Multiple Servers** — manage several instances from one dashboard | ✅ Available |
| ▶️ | **Auto-start** — configure servers to start always, never, or on last-state restore | ✅ Available |
| ⬆️ | **Fabricator self-update** — checks GitHub Releases; update from the sidebar or reinstall script | ✅ Available |
| ⌨️ | **CLI** (`fabricator` command) — start, stop, status, update, version, uninstall | ✅ Available |
| 🔄 | **One-click Minecraft / Fabric server updates** | 📋 Planned |

---

## Quick Start

### One-line installer (Linux)

The script downloads a **release tarball** from [GitHub Releases](https://github.com/philderks/Fabricator/releases), installs dependencies, creates a `fabricator` user and systemd unit, and starts the app. Supported distros: Debian/Ubuntu (and derivatives), Arch, Fedora/RHEL family. **systemd** and **curl** are required.

```bash
curl -fsSL https://fabricator.site/install.sh | bash
```

By default this installs the **latest** published release.

**Updating** an existing install (backs up `servers.json` and `fabricator.env`, replaces app files, keeps data under `/var/lib/fabricator`):

```bash
curl -fsSL https://fabricator.site/install.sh | bash -s -- --update
```

Or use the `fabricator` CLI:

```bash
fabricator update
```

After install, open `http://<host>:5000`. On first use the panel shows a one-time setup page to create the operator password — see [Authentication](#authentication). (The default packaged config also binds to all interfaces — use a firewall or reverse proxy if the host is internet-facing.)

For local development, the app defaults to loopback-only; see `.env.example`.

<details>
<summary>Manual installation</summary>

```bash
# Clone
git clone https://github.com/philderks/Fabricator.git
cd Fabricator

# Backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Frontend
cd frontend
npm install
npm run build
cd ..

# Run (development — serves API + built frontend from frontend/dist)
python3 run.py
```

Environment variables are documented in `.env.example`. For production-like paths, set `FLASK_ENV=production`, `SERVER_ROOT`, and `SERVER_INDEX_FILE` (see Configuration).

</details>

---

### Docker

A pre-built multi-arch image (`linux/amd64`, `linux/arm64`) is published to GHCR on every release.

**docker-compose.yml** (recommended):

```yaml
services:
  fabricator:
    image: ghcr.io/philderks/fabricator:latest
    container_name: fabricator
    restart: unless-stopped
    ports:
      - "127.0.0.1:5000:5000"   # Panel — host loopback only by default
    volumes:
      - fabricator-data:/data
    stop_grace_period: 60s
    environment:
      - FLASK_ENV=production
      # - PLAYIT_ENABLED=true   # auto-start the tunnel on boot

volumes:
  fabricator-data:
```

```bash
docker compose up -d
```

All persistent data (servers, backups, managed Java) lives in the `fabricator-data` volume. The image runs as an unprivileged `fabricator` user (uid 10001).

To expose the panel to the network, change the port mapping to `"5000:5000"` and put a reverse proxy with TLS in front. Do **not** change `HOST` inside the container — it must stay `0.0.0.0`.

---

### Windows

Download `Fabricator-<version>.exe` from [GitHub Releases](https://github.com/philderks/Fabricator/releases) and run it. The app starts a local server and opens the panel in your browser. No installation required.

---

## Requirements

| | Requirement |
|---|---|
| **Linux** | Debian/Ubuntu, Arch, or Fedora/RHEL; systemd; Python 3.10+ |
| **Docker** | Any host running Docker with `linux/amd64` or `linux/arm64` |
| **Windows** | Windows 10/11 — standalone `.exe`, no Python or Node required |
| **Node.js** | 20.x (frontend build only — not needed for Docker or Windows installs) |

---

## Configuration

The installer writes `/etc/fabricator/fabricator.env` (group `fabricator`, mode `0640`). Common variables:

```env
# Listen address — packaged default is all interfaces; use a reverse proxy in production
HOST=0.0.0.0
PORT=5000
FLASK_ENV=production

# Server instances and index (paths must be writable by the fabricator user)
SERVER_ROOT=/var/lib/fabricator/servers
SERVER_INDEX_FILE=/var/lib/fabricator/servers.json

# Optional: comma-separated origins for a separate dev UI or external frontends (no *)
# CORS_ORIGINS=https://dashboard.example.com

# playit.gg tunnel agent — set to "true" to start the agent automatically on boot.
# The agent creates a public tunnel so the server is reachable without port-forwarding.
PLAYIT_ENABLED=false
```

The playit.gg tunnel makes a server reachable without port forwarding. The installer
provisions the pinned, sha256-verified `playit` and `playit-cli` binaries automatically —
no separate step. Turn the tunnel on per server under **Server → Settings → Network** (or
**Overview → Public access**), which walks you through the one-time playit.gg account claim.
Set `PLAYIT_ENABLED=true` above only if you want it to auto-start on boot.

Managed Java runtimes are stored under `/var/lib/fabricator/java` by default when `FLASK_ENV=production`.

After editing, restart the service:

```bash
sudo systemctl restart fabricator
```

<details>
<summary>Filesystem layout</summary>

```
/opt/fabricator/app              # Application code (fabricator:fabricator)
/opt/fabricator/venv             # Python virtualenv (fabricator:fabricator)
/var/lib/fabricator              # Server data, backups, managed Java
/etc/fabricator/fabricator.env   # Config (root:fabricator, 0640)
/etc/systemd/system/fabricator.service
```

</details>

### Authentication

The management panel requires a login by default. On **first boot** (no
credential configured yet) it starts in a locked **setup mode**: open the panel
and you'll be taken to a one-time page to create the operator password — in the
browser, the same on Linux, Docker, and the Windows `.exe` (no terminal needed).
Until a password is set, only that page is reachable.

The session signing key is generated and persisted automatically on first boot;
the password is stored, hashed, in a `0600` `auth.json` in the data directory
next to `servers.json` (`/var/lib/fabricator` under systemd).

**Advanced / declarative setup.** You can skip the setup page by providing the
credential up front — useful for Docker/automation and recommended on untrusted
networks (see the security note):

1. Optionally pin `SECRET_KEY` to a fixed value (otherwise auto-generated):
   `python -c "import secrets; print(secrets.token_hex(32))"`
2. Generate a password hash and set `FABRICATOR_AUTH_PASSWORD_HASH`:
   - systemd install: `fabricator hash-password`
   - Docker / source: `python -m backend.auth hash`

Precedence: env hash > persisted file > setup mode (and for the signing key:
env > file > auto-generated).

To run **without** the built-in login (only if you front Fabricator with your
own reverse-proxy authentication), set `FABRICATOR_DISABLE_AUTH=1`. This is the
only supported way to disable it.

**Change or reset the password.** Once logged in, change it from the panel header
(**Change password**). Forgot it / locked out? Delete `auth.json` from the data
directory and restart — the app drops back into setup mode so you can set a new
one. The file lives next to `servers.json`: `/var/lib/fabricator/auth.json` under
systemd, `~/.fabricator/auth.json` in dev, `%APPDATA%\Fabricator\auth.json` on
Windows. (Deleting it only resets the password/key; your servers are untouched.)

> **Security note (trust-on-first-use).** The first-boot setup page is reachable
> by anyone who can reach the panel until the password is set. On an untrusted
> network, set `FABRICATOR_AUTH_PASSWORD_HASH` before first exposure instead of
> relying on the open setup page.

When Fabricator is served behind TLS, also set `FABRICATOR_SESSION_COOKIE_SECURE=1`
so the session cookie carries the `Secure` flag.

---

## CLI

The `fabricator` command is available after a Linux systemd install:

```
fabricator start          # Start the Fabricator service
fabricator stop           # Stop the Fabricator service
fabricator status         # Show service and API status
fabricator update         # Update to the latest release
fabricator version        # Print the installed version
fabricator hash-password  # Generate a password hash for FABRICATOR_AUTH_PASSWORD_HASH
fabricator uninstall      # Remove Fabricator and all its data
```

Most commands also accept `--json` for machine-readable output.

---

## Roadmap

| Status | Feature |
|---|---|
| ✅ Done | Mod management |
| ✅ Done | Logs & monitoring |
| ✅ Done | Backups & restore |
| ✅ Done | World import |
| ✅ Done | Multiple server instances |
| ✅ Done | Auto-start (always / never / last-state) |
| ✅ Done | Fabricator self-update (UI + installer + CLI) |
| ✅ Done | CLI (`fabricator` command) |
| ✅ Done | Docker image |
| ✅ Done | Windows support |
| 🔧 In progress | Additional loader support — NeoForge, Forge, Quilt, Paper |
| 📋 Planned | One-click Minecraft / Fabric server upgrades |

---

## Contributing

Bug reports and pull requests are welcome. For larger changes, open an issue first.

The frontend is Vue 3 + Vite in `/frontend`. The backend is Flask with blueprints under `/backend`; the process entrypoint is `run.py`. HTTP API details live in [API_DOCS.md](API_DOCS.md). Both halves can be run without the installer for local development.

---

## License

[GPL-3.0](LICENSE)
