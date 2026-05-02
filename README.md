<div align="center">

<img src="frontend/public/favicon.svg" alt="Fabricator Logo" width="92" height="92" />

# Fabricator

**Self-hosted web dashboard for managing Fabric-based Minecraft servers.**

[![License: GPL-3.0](https://img.shields.io/badge/license-GPL--3.0-blue?style=flat-square)](LICENSE)
[![Stars](https://img.shields.io/github/stars/philderks/Fabricator?style=flat-square)](https://github.com/philderks/Fabricator/stargazers)
[![Platform](https://img.shields.io/badge/platform-Linux-lightgrey?style=flat-square)](https://github.com/philderks/Fabricator)

[fabricator.derks.dev](https://fabricator.derks.dev/)

</div>

---

<!-- SCREENSHOT ─────────────────────────────────────────────────────────────
     Replace the img tag below with a GIF or PNG of the dashboard.
     Recommended: 1280×800 screen recording of the Overview page.
     Loop it: server start → logs ticking → mod install.
     Upload to /assets/ in the repo and update the path below.
─────────────────────────────────────────────────────────────────────────── -->
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
| 🔄 | **One-Click Server Updates** | 🔧 Coming soon |
| ⌨️ | **CLI** (`fabricator` command) | 🔧 Coming soon |

---

## Quick Start

### One-line installer

Supports Debian/Ubuntu, Arch, Fedora/RHEL.

```bash
curl -fsSL https://raw.githubusercontent.com/philderks/Fabricator/main/tools/install.sh | bash
```

Then open `http://localhost:5000`.

For remote access, set up a reverse proxy or use a [playit.gg](https://playit.gg) tunnel — Fabricator binds to `localhost` only by default.

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

# Start
python3 run.py
```

</details>

---

## Requirements

| | Requirement |
|---|---|
| OS | Linux — Debian/Ubuntu, Arch, or Fedora/RHEL |
| Java | 17+ (for the Minecraft server process) |
| Python | 3.10+ |
| Node.js | 20.x (build step only) |

> Windows is not supported yet.

---

## Configuration

The installer writes config to `/etc/fabricator/fabricator.env` (readable by the `fabricator` user, mode `0640`).

```env
# Port Fabricator listens on (default: 5000, localhost only)
PORT=5000

# Root directory for server instances
SERVERS_DIR=/var/lib/fabricator/servers
```

After editing, restart the service:

```bash
sudo systemctl restart fabricator
```

<details>
<summary>Filesystem layout</summary>

```
/opt/fabricator/app              # Application code (owned root:root)
/opt/fabricator/venv             # Python virtualenv (owned fabricator)
/var/lib/fabricator              # Server data and backups
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
| 🔧 In progress | CLI (`fabricator` command) |
| 📋 Planned | One-click server updates |
| 📋 Planned | Additional loader support |
| 📋 Planned | Windows support |

---

## Contributing

Bug reports and pull requests are welcome. For larger changes, open an issue first.

The frontend is Vue 3 + Vite (`/frontend`). The backend is Flask (`run.py`). Both run independently without the installer for local development.

---

## License

[GPL-3.0](LICENSE)
