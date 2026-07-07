---
title: Player management
description: Manage whitelist, operators, bans, IP bans, and online players.
---

The Players page combines live server commands with direct JSON file edits when the server is stopped.

## What the page shows

- Online players reported by the running Minecraft server.
- Known players from `usercache.json`.
- Whitelist entries from `whitelist.json`.
- Operators from `ops.json`.
- Player bans from `banned-players.json`.
- IP bans from `banned-ips.json`.
- Current whitelist/enforce-whitelist state.

## Name and reason validation

Fabricator validates player names before mutating files or sending commands:

- Player names must be 1–16 characters.
- Allowed characters are `A-Z`, `a-z`, `0-9`, and `_`.
- Reasons must be a single line and at most 256 characters.
- IP bans accept IPv4 addresses and wildcard segments such as `192.168.*.*`.

## Whitelist

Use the whitelist controls to add or remove players. Fabricator can also toggle runtime whitelist activity for a running server.

When the server is stopped, Fabricator updates files directly and patches `server.properties` for persisted enforcement changes.

## Operators

Operator level must be between 1 and 4.

Minecraft's running `op` command does not accept an op level. Fabricator therefore rejects attempts to set a non-default op level while the server is running. Stop the server before changing an existing operator's level.

## Bans and kicks

- Player bans and unbans accept a Minecraft player name.
- IP bans and unbans accept an IPv4 address or wildcard form.
- Kick requires the server to be running.

Prefer the Players page over raw console commands when possible because it validates inputs and returns clearer conflict messages.
