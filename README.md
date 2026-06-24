<div align="center">

<img src="frontend/public/favicon.svg" alt="Fabricator Logo" width="92" height="92" />

# Fabricator

**Self-hosted web dashboard for managing Minecraft servers.**

[![License: AGPL-3.0](https://img.shields.io/badge/license-AGPL--3.0-blue?style=flat-square)](LICENSE)
[![Stars](https://img.shields.io/github/stars/philderks/Fabricator?style=flat-square)](https://github.com/philderks/Fabricator/stargazers)
[![Platform](https://img.shields.io/badge/platform-Linux%20%7C%20Docker-lightgrey?style=flat-square)](https://github.com/philderks/Fabricator)
[![Docker](https://img.shields.io/badge/ghcr.io-philderks%2Ffabricator-2496ED?style=flat-square&logo=docker&logoColor=white)](https://github.com/philderks/Fabricator/pkgs/container/fabricator)

[Website](https://fabricator.site/) | [Documentation](https://docs.fabricator.site/)

</div>

---

<div align="center">
  <img width="2560" height="1313" alt="Overview" src="https://github.com/user-attachments/assets/7ed784e6-eb1d-4305-bc98-3800a785fbc1" />
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
| 🐳 | **Docker** — single multi-arch (amd64/arm64) image, runs as a non-root user | ✅ Available |
| ⬆️ | **Fabricator self-update** — checks GitHub Releases; update from the sidebar or reinstall script | ✅ Available |
| ⌨️ | **CLI** (`fabricator` command) — `status`, `start`/`stop`, `update`, `version`, `uninstall` | ✅ Available |
| 🔄 | **One-click Minecraft / Fabric server updates** | 🔧 Coming soon |

---

## Quick Start

### Docker (recommended)

A single multi-arch image is published to GHCR for every release. It runs as a
non-root user and keeps all state on one `/data` volume.

```bash
# Grab the compose file and start
curl -fsSL https://raw.githubusercontent.com/philderks/Fabricator/main/docker-compose.yml -o docker-compose.yml
docker compose up -d
```

The packaged `docker-compose.yml` publishes the panel to **host loopback only**
(`127.0.0.1:5000`). On first use you'll be prompted to create the operator password.
Minecraft server ports aren't published by default; use the built-in playit.gg tunnel,
or map each server's port explicitly (e.g. `25565:25565`).

To update, pull the new image and recreate the container — your data persists in
the named volume:

```bash
docker compose pull && docker compose up -d
```

Docker is the simplest way to run Fabricator on **Linux, macOS, or Windows** (via
Docker Desktop / WSL2).

### One-line installer

The script downloads a **release tarball** from [GitHub Releases](https://github.com/philderks/Fabricator/releases), installs dependencies, creates a `fabricator` user and systemd unit, and starts the app. Supported distros: Debian/Ubuntu (and derivatives), Arch, Fedora/RHEL family. **systemd** and **curl** are required.

```bash
curl -fsSL https://fabricator.site/install.sh | bash
```

By default this installs the **latest** published release.

**Updating** an existing install (backs up `servers.json` and `fabricator.env`, replaces app files, keeps data under `/var/lib/fabricator`):

```bash
curl -fsSL https://fabricator.site/install.sh | bash -s -- --update
```

After install, open `http://<host>:5000` (the default packaged config binds to all interfaces — use a firewall or reverse proxy if the host is reachable from untrusted networks).

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

## Requirements

| | Requirement |
|---|---|
| Docker | Any OS with Docker Engine / Docker Desktop (recommended path) |
| OS | Linux — Debian/Ubuntu, Arch, or Fedora/RHEL (systemd) for the native installer |
| Python | 3.10+ (manual/native install) |
| Node.js | 20.x (frontend build only) |

> The native installer targets Linux. On macOS and Windows, run Fabricator via Docker.

---

## Configuration

With Docker, set these as `environment:` entries in `docker-compose.yml`; the image already pins every data path onto the `/data` volume. For the native install, the installer writes `/etc/fabricator/fabricator.env` (group `fabricator`, mode `0640`). Common variables:

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
browser, the same on Linux and Docker (no terminal needed).
Until a password is set, only that page is reachable.

The session signing key is generated and persisted automatically on first boot;
the password is stored, hashed, in a `0600` `auth.json` in the data directory
next to `servers.json` (`/var/lib/fabricator` under systemd, `/data` in Docker).

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
systemd, `/data/auth.json` in Docker. (Deleting it only resets the password/key;
your servers are untouched.)

> **Security note (trust-on-first-use).** The first-boot setup page is reachable
> by anyone who can reach the panel until the password is set. On an untrusted
> network, set `FABRICATOR_AUTH_PASSWORD_HASH` before first exposure instead of
> relying on the open setup page.

When Fabricator is served behind TLS, also set `FABRICATOR_SESSION_COOKIE_SECURE=1`
so the session cookie carries the `Secure` flag.

---

## CLI

The native (systemd) install ships a `fabricator` command for managing the service from the shell:

```bash
fabricator status            # systemd state + Flask/Minecraft API reachability (--json available)
fabricator start | stop      # control the systemd service
fabricator update            # update to the latest GitHub release (runs the installer)
fabricator version           # show the installed version
fabricator hash-password     # generate a password hash for FABRICATOR_AUTH_PASSWORD_HASH
fabricator uninstall         # remove app, data, config, systemd unit, and service user
fabricator help              # list all commands
```

The read commands (`status`, `version`, `help`) accept `--json` for scripting. The CLI is currently minimal and will grow to cover server and mod management.

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
| ✅ Done | Loader support: Vanilla, NeoForge, Forge, Quilt, Fabric |
| ✅ Done | Docker image (multi-arch, non-root) + compose |
| ✅ Done | Fabricator self-update (UI + installer) |
| ✅ Done | CLI — minimal form (`status`, `start`/`stop`, `update`, `version`, `uninstall`) |
| 🔧 In progress | CLI — expanded server/mod management commands |
| 📋 Planned | One-click Minecraft / Fabric server upgrades |
| 📋 Planned | Native Windows installer (Docker works today) |

---

## Contributing

Bug reports and pull requests are welcome. For larger changes, open an issue first.

The frontend is Vue 3 + Vite in `/frontend`. The backend is Flask with blueprints under `/backend`; the process entrypoint is `run.py`. HTTP API details live in [API_DOCS.md](API_DOCS.md). Both halves can be run without the installer for local development.

---

## License

[AGPL-3.0](LICENSE)
