#!/usr/bin/env bash
set -euo pipefail

info()  { echo "[INFO]  $*"; }
warn()  { echo "[WARN]  $*" >&2; }
error() { echo "[ERROR] $*" >&2; exit 1; }

SERVICE_NAME="fabricator.service"
SERVICE_USER="fabricator"
INSTALL_DIR="/opt/fabricator"
DATA_DIR="/var/lib/fabricator"

# --- root/sudo detection ---
SUDO=""
if [ "$(id -u)" -ne 0 ]; then
    if command -v sudo >/dev/null 2>&1; then
        SUDO="sudo"
    else
        warn "This uninstaller needs root privileges (sudo not found)."
        error "Re-run as root or install sudo."
    fi
fi

# Stop and disable the systemd service
if $SUDO systemctl is-active --quiet "$SERVICE_NAME" 2>/dev/null; then
    info "Stopping $SERVICE_NAME..."
    $SUDO systemctl stop "$SERVICE_NAME"
fi
if $SUDO systemctl is-enabled --quiet "$SERVICE_NAME" 2>/dev/null; then
    info "Disabling $SERVICE_NAME..."
    $SUDO systemctl disable "$SERVICE_NAME"
fi

# Remove the systemd unit file and reload
$SUDO rm -f "/etc/systemd/system/$SERVICE_NAME"
$SUDO systemctl daemon-reload

# Remove application files
info "Removing application files at $INSTALL_DIR..."
$SUDO rm -rf "$INSTALL_DIR"

# Interactive prompts for data and config removal
read -rp "Remove runtime data at $DATA_DIR? [y/N] " remove_data
if [[ "$remove_data" =~ ^[Yy]$ ]]; then
    $SUDO rm -rf "$DATA_DIR"
    info "Removed $DATA_DIR"
fi

read -rp "Remove config at /etc/fabricator? [y/N] " remove_conf
if [[ "$remove_conf" =~ ^[Yy]$ ]]; then
    $SUDO rm -rf /etc/fabricator
    info "Removed /etc/fabricator"
fi

read -rp "Remove service user '$SERVICE_USER'? [y/N] " remove_user
if [[ "$remove_user" =~ ^[Yy]$ ]]; then
    $SUDO userdel "$SERVICE_USER"
    info "Removed user $SERVICE_USER"
fi

info "Fabricator uninstalled."
