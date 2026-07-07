---
title: Managing mods and modpacks
description: Install, remove, and organize mods from Modrinth in Fabricator.
---

Fabricator integrates with Modrinth for both mods and modpacks. The Mods page is available for modded loaders and is hidden for Vanilla servers.

## Installed mods

The Mods page lists JAR files from the server's `mods/` directory. Fabricator enriches installed JARs with Modrinth metadata when possible so the UI can show names, icons, versions, and sizes.

You can:

- Search within installed mods.
- Remove one mod.
- Select several mods and bulk delete them.
- Open the Modrinth browser to install new mods.
- Open the modpack browser to import a compatible modpack.

## Install a mod from Modrinth

1. Open a modded server.
2. Go to **Mods**.
3. Click **Browse mods**.
4. Search for a project.
5. Choose a result that matches your server's loader and Minecraft version.
6. Confirm install.

The backend resolves a compatible Modrinth version, downloads the primary file, places it into the server's `mods/` folder, and returns the installed filename/path.

## Dependency handling

When Modrinth reports required dependencies, Fabricator can surface them in the UI before installation. Review dependencies before confirming, especially on large mod sets.

## Modpacks

Use **Browse modpacks** from the Mods page. Fabricator searches Modrinth modpacks, resolves a compatible project version for the server's loader and Minecraft version, downloads the pack metadata, classifies server-side mods, and installs the required files.

The active modpack, when known, appears above the installed mods list.

## Compatibility notes

- Loader and Minecraft version are used as compatibility filters.
- Client-only projects are not useful on a dedicated server and may be skipped or warned about depending on metadata.
- Some projects use ambiguous side metadata; verify the server logs after installing a pack.
- Restart the Minecraft server after changing mods.

## API endpoints behind the page

The UI calls endpoints under `/api/modrinth/*` for search, project versions, compatible download resolution, installs, modpack installs, and install progress. Installed local files are managed through `/api/servers/<server_id>/mods`.
