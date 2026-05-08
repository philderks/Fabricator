#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_SCRIPT="${SCRIPT_DIR}/install.sh"

if [[ ! -f "$INSTALL_SCRIPT" ]]; then
  echo "[ERROR] install.sh not found at ${INSTALL_SCRIPT}" >&2
  exit 1
fi

# In-app updates are invoked as root via: sudo -n bash …/update.sh
# (see install.sh sudoers). No need to re-run apt/pacman/dnf every time;
# only pull the release tarball, sync, refresh venv, restart service.
export FABRICATOR_SKIP_OS_PACKAGES=1

# Optional pinned version without relying on the environment (needed after
# sudo, which resets the caller env by default).
if [[ -n "${1:-}" ]] && [[ "$1" != -* ]]; then
  export FABRICATOR_VERSION="$1"
  shift
fi

TARGET_VERSION="${FABRICATOR_VERSION:-latest}"
echo "[INFO] Starting Fabricator update (target: ${TARGET_VERSION})"
echo "[INFO] This update preserves server metadata and user config."
echo "[INFO] OS packages will not be refreshed (release-only update). Run install.sh manually if system deps changed."

exec bash "$INSTALL_SCRIPT" --update "$@"
