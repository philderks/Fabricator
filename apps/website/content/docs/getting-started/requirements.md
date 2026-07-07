---
title: Requirements
description: What you need before installing Fabricator.
---

## Operating system

Fabricator has two supported deployment paths: Docker on any Docker-capable host, or the native Linux installer on a systemd server. The native installer supports these distro families:

| Distro family | Package manager | Examples |
| --- | --- | --- |
| Debian / Ubuntu | `apt` | Debian, Ubuntu, Raspbian, Pop!_OS, Linux Mint |
| Arch | `pacman` | Arch, EndeavourOS, Garuda, Manjaro |
| Fedora / RHEL | `dnf` | Fedora, RHEL, CentOS, Rocky, AlmaLinux |

Other distros may work manually, but the official native installer exits on unknown families. On macOS and Windows, use Docker Desktop / WSL2 rather than the native installer.

## Host access

You need:

- Docker Engine / Docker Desktop for the container install, or root/`sudo` plus `curl` and `systemctl` for the native installer.
- Outbound HTTPS access to GitHub Releases, PyPI, Modrinth, and Adoptium.

The native installer creates a system user named `fabricator`, a systemd unit, `/etc/fabricator/fabricator.env`, and `/var/lib/fabricator`. The Docker image uses a non-root container user and persists data under `/data`.

## Runtime requirements

| Component | Requirement |
| --- | --- |
| Docker | Docker Engine or Docker Desktop for the recommended container install. |
| Python | Python 3.10+ at minimum for native/manual installs; the container uses Python 3.11. |
| Node.js | Not required at runtime for release tarballs or the Docker image; required for frontend builds from source. |
| Java | Managed per server by Fabricator. A global Java install is optional. |
| RAM | Fabricator itself is lightweight; size the host for your Minecraft servers. |
| Disk | Plan for worlds, mods, backups, and managed Java runtimes under `/var/lib/fabricator`. |

## Java compatibility rules

Fabricator maps Minecraft versions to Java requirements before install/start:

| Minecraft version | Java |
| --- | --- |
| `<= 1.16.5` | 8 |
| `1.17.x` | 16 |
| `1.18.x` through `1.20.4` | 17 |
| `1.20.5` through `1.21.x` | 21 |
| year-based `24.x+` and configured future `1.26+` | 25 |
| unmapped `1.22.x` through `1.25.x` | not enforced; Fabricator shows a warning |

Set `FABRICATOR_SKIP_JAVA_CHECK=1` only for local development/testing. Do not use it in production: servers may fail at runtime with the wrong JVM.

## Network ports

- Fabricator dashboard/API: `PORT` from `/etc/fabricator/fabricator.env` (default `5000`).
- Minecraft server: per-server `server-port` (default `25565`).
- Optional Minecraft query/RCON: per-server settings when enabled.
- Optional playit.gg tunnels: outbound HTTPS to playit.gg/API endpoints. No inbound Minecraft port-forward is required for servers exposed through playit.gg.

The packaged installer writes `HOST=0.0.0.0` by default so the dashboard binds all interfaces. If the host is reachable from untrusted networks, put Fabricator behind a firewall and reverse proxy. playit.gg can expose Minecraft server ports, but it does not protect the Fabricator dashboard itself.
