#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/fabricator"
SERVICE_FILE="/etc/systemd/system/fabricator.service"
SCRIPT_DIR=$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)
PROJECT_ROOT="${SCRIPT_DIR}/.."

if [[ $EUID -ne 0 ]]; then
  echo "This installer must be run as root (try: sudo bash tools/install.sh)."
  exit 1
fi

echo "Installing Fabricator to ${APP_DIR}"
rm -rf "${APP_DIR}"
mkdir -p "${APP_DIR}"

# Copy project files
cp -r "${PROJECT_ROOT}"/. "${APP_DIR}"/

# Create virtual environment and install dependencies
python3 -m venv "${APP_DIR}/venv"
"${APP_DIR}/venv/bin/pip" install --upgrade pip
"${APP_DIR}/venv/bin/pip" install -r "${APP_DIR}/requirements.txt"

# Write systemd service
cat > "${SERVICE_FILE}" <<EOF
[Unit]
Description=Fabricator Server
After=network.target

[Service]
Type=simple
WorkingDirectory=${APP_DIR}/backend
ExecStart=${APP_DIR}/venv/bin/python -m fabricator_backend
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now fabricator.service

echo "Fabricator is running at http://127.0.0.1:8000"
