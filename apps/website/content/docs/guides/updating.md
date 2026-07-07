---
title: Updating
description: Keep Fabricator, Minecraft servers, and mod sets up to date safely.
---

Fabricator has three different update surfaces: the Fabricator app, Minecraft server files/loaders, and mods or modpacks. Treat them separately and take backups first.

## Update Fabricator

Recommended options:

```bash
fabricator update
```

or:

```bash
curl -fsSL https://fabricator.site/install.sh | bash -s -- --update
```

The dashboard can also trigger a self-update when GitHub Releases reports a newer version. In-app updates run the bundled `tools/update.sh` wrapper through a limited sudoers rule installed at `/etc/sudoers.d/fabricator-self-update`.

Before replacing app files, update mode backs up important state into `/var/lib/fabricator/update-backups/<timestamp>/`.

## Check current version

```bash
fabricator version
fabricator status
```

The CLI reads `/opt/fabricator/app/.fabricator_version` and checks local API reachability.

## Update Minecraft or loader versions

Changing the Minecraft version or loader for an existing server is not currently a one-click in-place upgrade. The server settings page treats **Running Version** and **Mod Loader** as read-only and notes that changes require reinstall.

Safer workflow:

1. Create a backup snapshot of the existing server.
2. Create a new server with the target Minecraft/loader version.
3. Copy or restore the world and required files intentionally.
4. Reinstall compatible mods or modpack version.
5. Test startup and logs before removing the old server.

## Update mods

Fabricator can install and remove mods, but automatic bulk mod updates are not the same as Minecraft server upgrades. Before changing a mod set:

1. Stop the server.
2. Create a backup.
3. Install/remove mods from the Mods page.
4. Start the server and inspect Console logs.
5. If startup fails, remove the last changed mod or restore the backup.

## Rollback

Use the Backups page to restore a snapshot. Restore modes include replacing the server contents, merging files into the existing directory, or restoring to a sibling directory depending on the mode offered by the UI.
