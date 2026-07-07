---
title: Server settings
description: Edit Minecraft server.properties from Fabricator.
---

The Settings page edits the server metadata Fabricator stores and writes corresponding values into `server.properties`.

## Editing rules

Settings are editable only while the server is stopped. If the server is running, the page displays a guard and disables edits. This avoids writing `server.properties` values that Minecraft will not reload until restart.

The page has two modes:

- **Basic mode:** common identity, gameplay, world, player, and networking options.
- **Expert mode:** advanced/risky properties such as compression, native transport, resource packs, query/RCON, JMX, text filtering, and low-level limits.

## Read-only values

These fields are shown but not edited from Settings:

- Running Minecraft version
- Mod loader

Changing either requires a reinstall/new server workflow rather than a settings save.

## Common field groups

| Group | Examples |
| --- | --- |
| Server identity | name, MOTD, bug report URL, port, bind address, max players |
| Gameplay | difficulty, gamemode, hardcore, PVP, flight, command blocks |
| World generation | level name, level type, seed, generator settings, structures |
| Performance | view distance, simulation distance, max tick time, compression threshold |
| Security/status | online mode, secure profile, whitelist, status, query, RCON |
| Resource packs | URL, SHA-1, prompt, UUID, require-resource-pack |

## How saves work

When you save settings, Fabricator updates the server record and writes a fresh `server.properties` file into the server install directory. Boolean values are written as lowercase `true` or `false`.

If a file write fails, the API returns an error and the UI keeps the unsaved state visible.
