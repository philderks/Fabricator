---
title: File manager
description: Browse and edit server files safely from the dashboard.
---

The Files page lets you navigate inside a selected server's install directory and edit UTF-8 text files.

## Path safety

Fabricator resolves every file path relative to the server's install path and rejects attempts to escape that directory. This protects the host from browser requests such as `../../etc/passwd`.

## Browsing

Directory listings include:

- File or directory name.
- Size in bytes.
- Last modified timestamp.
- Relative path from the server root.
- `isDir` flag.

Directories are sorted before files.

## Reading and editing files

Fabricator can read and write UTF-8 text files. Binary or non-UTF-8 files are rejected for text reads. Writes require the server lock, so Fabricator will not edit a file while another mutating operation is active.

Good candidates for the file editor:

- `server.properties`
- `whitelist.json`, `ops.json`, and ban files when you know what you are doing
- Mod/plugin config text files
- Logs or generated text files for inspection

Avoid editing large binary files, region files, JARs, or archives through the text editor.

## Related endpoints

- `GET /api/servers/<server_id>/files?path=<relative-dir>`
- `GET /api/servers/<server_id>/files/content?path=<relative-file>`
- `PUT /api/servers/<server_id>/files/content`
