<div align="center">

<img src="frontend/public/favicon.svg" alt="Fabricator Logo" width="92" height="92" />

# Fabricator

**Self-hosted web dashboard for managing Fabric-based Minecraft servers.**

[![License: GPL-3.0](https://img.shields.io/badge/license-GPL--3.0-blue?style=flat-square)](LICENSE)
[![Stars](https://img.shields.io/github/stars/philderks/Fabricator?style=flat-square)](https://github.com/philderks/Fabricator/stargazers)
[![Platform](https://img.shields.io/badge/platform-Linux-lightgrey?style=flat-square)](https://github.com/philderks/Fabricator)

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
| 📦 | **Mod Management** — install, remove, and browse Fabric mods | ✅ Available |
| 📋 | **Logs & Monitoring** — live log stream, TPS and RAM graphs | ✅ Available |
| 💾 | **Backups & Restore** — manual snapshots, restore from any backup | ✅ Available |
| 🖥️ | **Multiple Servers** — manage several instances from one dashboard | ✅ Available |
| ⬆️ | **Fabricator self-update** — checks GitHub Releases; update from the sidebar or reinstall script | ✅ Available |
| 🔄 | **One-click Minecraft / Fabric server updates** | 🔧 Coming soon |
| ⌨️ | **CLI** (`fabricator` command) | 🔧 Coming soon |

---

## Quick Start

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
| OS | Linux — Debian/Ubuntu, Arch, or Fedora/RHEL (systemd) |
| Python | 3.10+ |
| Node.js | 20.x (frontend build only) |

> Windows is not supported yet.

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
```

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

---

## Roadmap

| Status | Feature |
|---|---|
| ✅ Done | Mod management |
| ✅ Done | Logs & monitoring |
| ✅ Done | Backups & restore |
| ✅ Done | Multiple server instances |
| ✅ Done | Fabricator self-update (UI + installer) |
| 🔧 In progress | CLI (`fabricator` command) |
| 📋 Planned | One-click Minecraft / Fabric server upgrades |
| 📋 Planned | Additional loader support |
| 📋 Planned | Windows support |

---

## Contributing

Bug reports and pull requests are welcome. For larger changes, open an issue first.

The frontend is Vue 3 + Vite in `/frontend`. The backend is Flask with blueprints under `/backend`; the process entrypoint is `run.py`. HTTP API details live in [API_DOCS.md](API_DOCS.md). Both halves can be run without the installer for local development.

---

## License

[GPL-3.0](LICENSE)
