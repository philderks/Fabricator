---
title: Backups and restore
description: Create manual and scheduled backups, download snapshots, and restore servers.
---

Fabricator supports quick backups, scheduled backup configurations, snapshot downloads, restore jobs, and world imports.

## Quick backups

Use a quick backup when you want an immediate snapshot before risky work such as installing mods, changing settings, or updating Fabricator.

Quick backup options include:

- Custom storage path.
- Compression on/off.
- Flush before backup.
- Shutdown during backup.

The backend starts a background backup job and returns a job id. The UI polls that job until it completes.

## Backup configurations

A backup configuration defines reusable settings such as name, storage path, maximum snapshots, and optional schedule. When a schedule is present, Fabricator registers it with the background scheduler and reports the next run time in the UI.

Deleting a backup configuration does not silently orphan files. The delete response reports retained and deleted archive paths. If `purge=1` is used, Fabricator only deletes archives that both belong to that config's snapshot records and live inside the config's storage path.

## Snapshots

Snapshots can be listed, deleted, downloaded, or restored. Downloads support the original tar archive and a browser-friendly ZIP conversion.

ZIP conversion handles Fabricator's hybrid archives by unpacking nested data/world tar files into a flat ZIP tree. Region files are stored without recompression because Minecraft region files are already compressed.

## Restore modes

Restore is a background job. The UI asks for a restore mode before starting it. Use the most conservative mode available when you are unsure, and keep a fresh backup before replacing files.

## Import world

Use **Backups → Import world** to upload an existing Minecraft world archive and replace the server's active world. Fabricator accepts `.zip`, `.tar`, and `.tar.gz` archives that contain a `level.dat`. It supports both server-style worlds (`world/`, `world_nether/`, `world_the_end/`) and singleplayer saves with `DIM-1` / `DIM1` directories.

World import is a background job. Fabricator stops the server if it is running, writes a mandatory safety snapshot under the server's `backups` directory before touching live world files, extracts the upload into staging with traversal-safe archive handling, swaps the normalized world directories into place, and restarts the server if it was running before the import.

The default upload cap is 10 GiB. Change `FABRICATOR_MAX_WORLD_UPLOAD_BYTES` if needed, and raise any reverse-proxy request body limit too.

## Job polling

Backup, restore, and world-import jobs are globally identified by UUID. Poll progress with:

```text
GET /api/backup-jobs/<job_id>
```

The response includes `active` plus the current progress payload.
