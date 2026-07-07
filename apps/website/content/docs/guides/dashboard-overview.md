---
title: Dashboard overview
description: Tour the Fabricator web dashboard and its main sections.
---

The dashboard is organized around a selected server. The root page lists servers; once you open one, the sidebar shows server-specific sections.

## Server list and switcher

The root dashboard displays all servers from Fabricator's server index. Use it to create a server, open an existing one, or switch context later with the sidebar server switcher.

A server record includes identity, loader, Minecraft version, install path, memory, status, Java compatibility metadata, and the settings used to write `server.properties`.

## Server sections

| Section | Purpose |
| --- | --- |
| Overview | Runtime state, basic stats, quick lifecycle actions, and status summary. |
| Console | Recent stdout/stderr and command input for running servers. |
| Players | Online/known players, whitelist, ops, bans, IP bans, and kick actions. |
| Mods | Installed JARs, Modrinth mod search, modpack import, and bulk delete. Hidden for Vanilla servers. |
| Files | Browse directories and edit UTF-8 text files inside the server install path. |
| Backups | Snapshot list, scheduled backup configs, quick backups, restore, and download. |
| playit.gg | Shared tunnel-agent controls and this server's public address, matched by Minecraft port. |
| Settings | Basic and expert `server.properties` editor. |

## Runtime state

Fabricator stores the desired/persisted state in `servers.json` and augments it with live process state from an in-memory process registry. During long operations such as installation, start, stop, and restore, the persisted transitional state is preserved so the UI does not accidentally show a server as ready while a lock is still active.

## Concurrency model

Operations that mutate a server use a per-server lock. If another operation is already running, Fabricator returns a conflict instead of modifying the same files concurrently. This matters for installs, settings writes, file writes, player changes, backups, restore, and lifecycle operations.

## Self-update indicator

The sidebar polls GitHub Releases periodically. When an update is available, the dashboard can trigger the bundled update wrapper. While an update is running, polling becomes more frequent and a toast reports the result.
