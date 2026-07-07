---
title: Console
description: Use the Fabricator server console from the dashboard.
---

The Console page shows recent Minecraft server output and lets you send commands to a running server.

## Reading logs

Fabricator captures stdout and stderr from the managed Minecraft process. The backend returns a bounded tail so the browser can show recent output without loading large log files.

If the server is not running, the logs endpoint returns an empty/not-running response rather than reading historical files from disk.

## Sending commands

Use the command input to send Minecraft console commands. Do not include a leading slash; send commands as the server console would receive them, for example:

```text
say Server restart in 5 minutes
whitelist list
save-all
```

Fabricator writes the command to the running process stdin. If no process is registered for the server, the API returns an error.

## Safe operation tips

- Confirm you selected the correct server in the sidebar before sending destructive commands.
- Use `save-all` before manual maintenance when you are not sure whether autosave is current.
- Prefer the Players page for whitelist, op, ban, and kick workflows; it validates names and handles stopped-server file edits where needed.
- Prefer the Backups page before large config or mod changes.

## Related endpoints

- `GET /api/servers/<server_id>/logs?limit=200`
- `POST /api/servers/<server_id>/console`
