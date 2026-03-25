#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_SCRIPT="${SCRIPT_DIR}/install.sh"

if [[ ! -f "$INSTALL_SCRIPT" ]]; then
  echo "[ERROR] install.sh not found at ${INSTALL_SCRIPT}" >&2
  exit 1
fi

TARGET_VERSION="${FABRICATOR_VERSION:-latest}"
echo "[INFO] Starting Fabricator update (target: ${TARGET_VERSION})"
echo "[INFO] This update preserves server metadata and user config."

exec bash "$INSTALL_SCRIPT" --update "$@"
