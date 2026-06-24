#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_SCRIPT="${SCRIPT_DIR}/install.sh"

if [[ ! -f "$INSTALL_SCRIPT" ]]; then
  echo "[ERROR] install.sh not found at ${INSTALL_SCRIPT}" >&2
  exit 1
fi

# In-app updates are invoked as root by the fabricator-update.service oneshot,
# triggered when the unprivileged panel drops a request file watched by
# fabricator-update.path (see install.sh). No need to re-run apt/pacman/dnf
# every time; only pull the release tarball, sync, refresh venv, restart service.
export FABRICATOR_SKIP_OS_PACKAGES=1

# Pinned version, in order of precedence:
#   1) explicit positional arg (manual `bash update.sh 1.2.3`)
#   2) request file written by the panel (FABRICATOR_UPDATE_REQUEST_FILE)
# The request file is attacker-controllable (written by the unprivileged panel
# user), so its contents are validated against a strict allowlist before use —
# this is the trust boundary between the panel and the root updater.
if [[ -n "${1:-}" ]] && [[ "$1" != -* ]]; then
  export FABRICATOR_VERSION="$1"
  shift
elif [[ -n "${FABRICATOR_UPDATE_REQUEST_FILE:-}" ]] && [[ -f "$FABRICATOR_UPDATE_REQUEST_FILE" ]]; then
  REQUESTED_VERSION="$(head -n1 "$FABRICATOR_UPDATE_REQUEST_FILE" | tr -d '[:space:]')"
  if [[ -n "$REQUESTED_VERSION" ]]; then
    if [[ "$REQUESTED_VERSION" =~ ^[A-Za-z0-9._-]+$ ]]; then
      export FABRICATOR_VERSION="$REQUESTED_VERSION"
    else
      echo "[ERROR] Rejecting malformed version in request file: ${REQUESTED_VERSION}" >&2
      exit 2
    fi
  fi
fi

TARGET_VERSION="${FABRICATOR_VERSION:-latest}"
echo "[INFO] Starting Fabricator update (target: ${TARGET_VERSION})"
echo "[INFO] This update preserves server metadata and user config."
echo "[INFO] OS packages will not be refreshed (release-only update). Run install.sh manually if system deps changed."

exec bash "$INSTALL_SCRIPT" --update "$@"
