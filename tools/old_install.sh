#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/srv/fabricator"
SERVICE_FILE="/etc/systemd/system/fabricator.service"
SCRIPT_DIR=$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)
PROJECT_ROOT="${SCRIPT_DIR}/.."

if [[ $EUID -ne 0 ]]; then
  echo "Run as root: sudo bash tools/install.sh"
  exit 1
fi

echo "Installing Fabricator to ${APP_DIR}..."

rm -rf "${APP_DIR}"
mkdir -p "${APP_DIR}"

# Projekt kopieren
cp -r "${PROJECT_ROOT}"/. "${APP_DIR}"/

cd "${APP_DIR}"

# venv + deps
python3 -m venv venv
venv/bin/pip install --upgrade pip
venv/bin/pip install -r requirements.txt

# Frontend build
cd frontend
npm install
npm run build
cd ..

# systemd Unit
cat > "${SERVICE_FILE}" <<EOF
[Unit]
Description=Fabricator Server
After=network.target

[Service]
Type=simple
WorkingDirectory=${APP_DIR}
ExecStart=${APP_DIR}/venv/bin/python run.py
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now fabricator.service

echo "Fabricator is running at http://127.0.0.1:5000"
