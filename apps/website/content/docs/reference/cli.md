---
title: CLI
description: Command-line interface reference for Fabricator.
---

The Fabricator CLI is a small [Click](https://click.palletsprojects.com/) program for **system-level** service management on a standard Linux install. It drives `systemctl`, reads the installed version marker, talks to the local HTTP API for status, runs the bundled update script, and can remove an installation.

Source code lives in the main repo: [`tools/cli.py`](https://github.com/philderks/Fabricator/blob/main/tools/cli.py).

## Prerequisites

Commands assume a standard deployment where:

- Fabricator runs as the `fabricator` systemd service.
- The app lives under `/opt/fabricator/app`.
- The virtualenv lives under `/opt/fabricator/venv`.
- The local API is reachable at `http://localhost:5000`.
- `/usr/local/bin/fabricator` points to the CLI entry point installed by `pip install -e /opt/fabricator/app`.

## Commands

### `fabricator start`

Runs `systemctl start fabricator`.

- Success: prints a green success message and exits `0`.
- Failure: prints a red error and exits with the `systemctl` return code.

### `fabricator stop`

Runs `systemctl stop fabricator`.

The command does not call a Flask shutdown endpoint; it delegates service shutdown to systemd.

### `fabricator update`

Updates Fabricator to the latest GitHub release.

1. Reads `/opt/fabricator/app/.fabricator_version` when present.
2. Fetches `https://api.github.com/repos/philderks/Fabricator/releases/latest`.
3. If already up to date, exits successfully.
4. Otherwise runs `bash /opt/fabricator/app/tools/install.sh --update` with `FABRICATOR_VERSION` set to the latest tag.

### `fabricator status`

Shows systemd state and local Flask/API reachability.

Options:

| Option | Description |
| --- | --- |
| `--json` | Print a JSON object instead of formatted text. |

Human output includes:

- `Service`: result of `systemctl is-active fabricator`.
- `Flask`: whether `GET http://localhost:5000/api/status` responds within five seconds.
- Optional Minecraft-ish keys (`players`, `tps`, `uptime`) when the API response includes them.

JSON shape:

```json
{
  "systemd_state": "active",
  "flask_up": true,
  "api_status_code": 200,
  "api_body": {}
}
```

### `fabricator version`

Prints the installed Fabricator release tag from `/opt/fabricator/app/.fabricator_version`.

Options:

| Option | Description |
| --- | --- |
| `--json` | Print `{ "version": "<tag or null>" }`. |

### `fabricator uninstall`

Destructively removes Fabricator. It prompts for `yes` before proceeding.

The command attempts, in order:

1. Stop the service.
2. Disable the service.
3. Remove `/opt/fabricator`.
4. Remove `/var/lib/fabricator`.
5. Remove `/etc/fabricator`.
6. Remove the `fabricator` service user.
7. Remove the systemd unit.
8. Run `systemctl daemon-reload`.

Individual removal steps report warnings rather than aborting the whole sequence.

### `fabricator help`

Lists every registered subcommand and short description.

Options:

| Option | Description |
| --- | --- |
| `--json` | Print a JSON array of `{ "command", "description" }` objects. |

Use Click's built-in help for command-specific flags:

```bash
fabricator status --help
fabricator update --help
```

## Summary

| Command | Purpose |
| --- | --- |
| `start` | Start the systemd service. |
| `stop` | Stop the systemd service. |
| `update` | Update to latest GitHub release via installer update mode. |
| `status` | Show service/API health, optionally as JSON. |
| `version` | Read installed release marker, optionally as JSON. |
| `uninstall` | Interactive destructive removal. |
| `help` | List commands, optionally as JSON. |
