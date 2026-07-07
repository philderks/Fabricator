# Fabricator Agent Notes

Fabricator is a self-hosted Minecraft server manager. Keep this file minimal; it is only here to orient agents before they read the relevant code or docs.

## Structure

- `apps/backend/` - Python backend for auth, server management, Modrinth, backups, playit, and system utilities.
- `apps/cli/` - Fabricator CLI package and CLI tests.
- `apps/frontend/` - Product dashboard frontend.
- `apps/website/` - Marketing site and Fumadocs documentation site.
- `apps/website/content/docs/` - Canonical docs content. Start with `index.mdx`, `meta.json`, and each section's `meta.json`.
- `apps/website/content/docs/contributing/` - Contributor and development workflow docs.
- `tests/` - Repo-level tests.
- `tools/`, `docker/`, `Dockerfile`, `docker-compose.yml` - Install, release, and deployment support.
- `assets/` - Shared project assets.

Ignore generated dependency/build folders such as `node_modules`, `dist`, `.output`, `.tanstack`, and `.source` unless debugging generated output.

## Docs

When changing user-facing behavior, install steps, configuration, CLI/API behavior, troubleshooting, architecture, or contributor workflow, update the matching docs in `apps/website/content/docs/` in the same change.
