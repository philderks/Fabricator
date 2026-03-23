#!/usr/bin/env bash
set -euo pipefail

main() {
    info()  { echo "[INFO]  $*"; }
    warn()  { echo "[WARN]  $*" >&2; }
    error() { echo "[ERROR] $*" >&2; exit 1; }

    OS_FAMILY=""
    PACKAGETYPE=""

    GITHUB_OWNER="philderks"
    GITHUB_REPO="Fabricator"
    INSTALL_DIR="/opt/fabricator"
    APP_DIR="$INSTALL_DIR/app"
    VENV_DIR="$INSTALL_DIR/venv"
    SERVICE_USER="fabricator"
    SERVICE_NAME="fabricator.service"
    DATA_DIR="/var/lib/fabricator"

    FABRICATOR_REPO="${FABRICATOR_REPO:-${GITHUB_OWNER}/${GITHUB_REPO}}"
    FABRICATOR_BRANCH="${FABRICATOR_BRANCH:-main}"
    FABRICATOR_VERSION="${FABRICATOR_VERSION:-latest}"  # latest | main | v1.2.3
    APP_SUBDIR="${APP_SUBDIR:-}"                        # e.g. "backend" if run.py lives there

    if [ -f "$APP_DIR/.fabricator_version" ]; then
        EXISTING_VERSION="$(cat "$APP_DIR/.fabricator_version")"
        info "Existing Fabricator install detected (version: $EXISTING_VERSION). Upgrading..."
    else
        info "No existing install detected. Performing fresh install..."
    fi

    # --- root/sudo detection ---
    SUDO=""
    if [ "$(id -u)" -ne 0 ]; then
        if command -v sudo >/dev/null 2>&1; then
            SUDO="sudo"
        else
            warn "This installer needs root privileges (sudo not found)."
            error "Re-run as root or install sudo."
        fi
    fi

    # --- basic tool checks ---
    if ! command -v curl >/dev/null 2>&1; then
        error "curl is required to download Fabricator."
    fi
    if ! command -v systemctl >/dev/null 2>&1; then
        error "systemctl not found. This installer currently requires systemd."
    fi

    # 1) Detect distro (via /etc/os-release)
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        case "$ID" in
            debian|ubuntu|raspbian|pop|linuxmint)
                OS_FAMILY="debian"
                PACKAGETYPE="apt"
                ;;
            arch|endeavouros|garuda|manjaro)
                OS_FAMILY="arch"
                PACKAGETYPE="pacman"
                ;;
            fedora|rhel|centos|rocky|almalinux)
                OS_FAMILY="rhel"
                PACKAGETYPE="dnf"
                ;;
            *)
                OS_FAMILY="unknown"
                ;;
        esac
    fi

    if [ -z "$OS_FAMILY" ] || [ "$OS_FAMILY" = "unknown" ]; then
        warn "Unsupported or unknown Linux distro (ID=${ID:-unknown})."
        error "Supported so far: Debian/Ubuntu, Arch, Fedora-family."
    fi

    # 2) Install dependencies
    # NOTE: all package-manager commands redirect stdin from /dev/null so they
    # cannot consume the piped script when invoked via  curl … | bash
    info "Installing dependencies for $OS_FAMILY (pkg: $PACKAGETYPE)..."

    case "$PACKAGETYPE" in
        apt)
            DEPS="python3 python3-venv python3-pip openjdk-17-jre curl ca-certificates grep sed tar rsync"
            $SUDO apt-get update </dev/null
            $SUDO apt-get install -y $DEPS </dev/null
            # Node.js 18+ required for Vue/Vite frontend; use NodeSource on Debian/Ubuntu
            node_ver="$(node -v 2>/dev/null | sed 's/v//' | cut -d. -f1 || true)"
            if [ -z "$node_ver" ] || [ "$node_ver" -lt 18 ]; then
                info "Installing Node.js 20.x from NodeSource..."
                # Download the setup script to a temp file instead of piping directly
                # to bash. This lets the script be inspected before execution and
                # prints a checksum the operator can verify against a known-good value.
                SETUP_SCRIPT="$(mktemp)"
                curl -fsSL https://deb.nodesource.com/setup_20.x -o "$SETUP_SCRIPT"
                info "NodeSource setup script SHA256: $(sha256sum "$SETUP_SCRIPT" | cut -d' ' -f1)"
                if [ -n "$SUDO" ]; then
                    $SUDO -E bash "$SETUP_SCRIPT"
                else
                    bash "$SETUP_SCRIPT"
                fi
                rm -f "$SETUP_SCRIPT"
                $SUDO apt-get install -y nodejs </dev/null
            fi
            ;;
        pacman)
            DEPS="python python-pip jre-openjdk nodejs npm curl ca-certificates grep sed tar rsync"
            $SUDO pacman -Sy --noconfirm $DEPS </dev/null
            ;;
        dnf)
            DEPS="python3 python3-pip java-17-openjdk nodejs npm curl ca-certificates grep sed tar rsync"
            $SUDO dnf install -y $DEPS </dev/null
            ;;
        *)
            error "internal error: unknown PACKAGETYPE: $PACKAGETYPE"
            ;;
    esac

    info "Dependencies installed."

    # Create service user if missing
    info "Ensuring service user '$SERVICE_USER' exists..."
    if ! id "$SERVICE_USER" >/dev/null 2>&1; then
        $SUDO useradd --system --home "$DATA_DIR" --shell /usr/sbin/nologin "$SERVICE_USER"
    fi
    $SUDO mkdir -p "$DATA_DIR"
    $SUDO chown "$SERVICE_USER:$SERVICE_USER" "$DATA_DIR"
    $SUDO chmod 0750 "$DATA_DIR"

    # Helper to run commands as the service user
    run_as_service_user() {
        if [ "$(id -u)" -eq 0 ]; then
            su -s /bin/bash - "$SERVICE_USER" -c "$(printf '%q ' "$@")"
        else
            $SUDO -u "$SERVICE_USER" "$@"
        fi
    }

    # 3) Download Fabricator sources
    info "Downloading Fabricator from GitHub..."
    TMP_DIR="$(mktemp -d)"
    cleanup() { rm -rf "$TMP_DIR"; }
    trap cleanup EXIT

    get_latest_tag() {
      curl -fsSL "https://api.github.com/repos/${FABRICATOR_REPO}/releases/latest" \
        | grep -m1 '"tag_name"' \
        | sed -E 's/.*"tag_name":[[:space:]]*"([^"]+)".*/\1/'
    }

    download_tarball() {
      local kind="$1"   # "tags" or "heads"
      local ref="$2"    # tag or branch
      local url="https://github.com/${FABRICATOR_REPO}/archive/refs/${kind}/${ref}.tar.gz"

      info "Fetching: $url"
      curl -fsSL "$url" -o "$TMP_DIR/fabricator.tar.gz"
      tar -xzf "$TMP_DIR/fabricator.tar.gz" -C "$TMP_DIR"
    }

    if [[ "$FABRICATOR_VERSION" == "main" ]]; then
      download_tarball "heads" "$FABRICATOR_BRANCH"
    else
      TAG=""
      if [[ "$FABRICATOR_VERSION" == "latest" ]]; then
        TAG="$(get_latest_tag || true)"
      else
        TAG="$FABRICATOR_VERSION"
      fi

      if [[ -z "$TAG" ]]; then
        warn "WARNING: Could not determine latest release tag (GitHub API may be rate-limited or blocked)."
        warn "Falling back to branch: ${FABRICATOR_BRANCH}"
        download_tarball "heads" "$FABRICATOR_BRANCH"
      else
        info "Latest release tag: $TAG"
        download_tarball "tags" "$TAG"
      fi
    fi

    SRC_DIR="$(find "$TMP_DIR" -maxdepth 1 -type d -name 'Fabricator-*' | head -n1)"
    if [[ -z "${SRC_DIR:-}" || ! -d "$SRC_DIR" ]]; then
      error "ERROR: Could not locate extracted Fabricator sources."
    fi

    info "Source extracted to: $SRC_DIR"

    # Select app subdirectory if needed
    APP_SRC_DIR="$SRC_DIR"
    if [[ -n "$APP_SUBDIR" ]]; then
      APP_SRC_DIR="$SRC_DIR/$APP_SUBDIR"
    fi

    if [[ ! -d "$APP_SRC_DIR" ]]; then
      warn "ERROR: App source directory not found: $APP_SRC_DIR"
      error "Hint: set APP_SUBDIR (e.g. APP_SUBDIR=backend) if your run.py is not at repo root."
    fi

    # Sync into install location
    if $SUDO systemctl is-active --quiet "$SERVICE_NAME" 2>/dev/null; then
        info "Stopping running Fabricator service before update..."
        $SUDO systemctl stop "$SERVICE_NAME"
    fi
    $SUDO mkdir -p "$APP_DIR"
    $SUDO rsync -a --delete "$APP_SRC_DIR/" "$APP_DIR/"
    $SUDO chown -R root:root "$APP_DIR"
    $SUDO chmod -R 755 "$APP_DIR"
    $SUDO chown -R "$SERVICE_USER:$SERVICE_USER" "$VENV_DIR"

    if [[ -n "${TAG:-}" ]]; then
        echo "$TAG" | $SUDO tee "$APP_DIR/.fabricator_version" >/dev/null
    else
        echo "$FABRICATOR_BRANCH" | $SUDO tee "$APP_DIR/.fabricator_version" >/dev/null
    fi

    # Sanity check
    if [[ ! -f "$APP_DIR/run.py" ]]; then
      warn "ERROR: $APP_DIR/run.py not found after sync."
      error "Your app may live in a subfolder. Re-run with: APP_SUBDIR=<folder>"
    fi

    # 4a) Setup Python venv + requirements
    info "Creating Python virtualenv..."
    run_as_service_user python3 -m venv "$VENV_DIR"
    run_as_service_user "$VENV_DIR/bin/pip" install --upgrade pip </dev/null

    if [ -f "$APP_DIR/requirements.txt" ]; then
        info "Installing Python requirements..."
        run_as_service_user "$VENV_DIR/bin/pip" install -r "$APP_DIR/requirements.txt" </dev/null
    else
        info "No requirements.txt found in $APP_DIR, skipping pip install."
    fi

    # 4b) Build frontend (Vue/Vite)
    if [ -d "$APP_DIR/frontend" ] && [ -f "$APP_DIR/frontend/package.json" ]; then
        info "Building frontend..."
        run_as_service_user sh -c "cd \"$APP_DIR/frontend\" && npm ci && npm run build" </dev/null
    else
        info "No frontend folder found, skipping frontend build."
    fi

    # Config
    info "Creating config directory /etc/fabricator..."
    $SUDO mkdir -p /etc/fabricator

    ENV_FILE="/etc/fabricator/fabricator.env"
    if [ ! -f "$ENV_FILE" ]; then
        info "Creating default env file at $ENV_FILE"
        $SUDO tee "$ENV_FILE" >/dev/null <<EOF
# Fabricator environment configuration
# Listens on localhost only. Fabricator will not be reachable from other
# machines without a reverse proxy (e.g. nginx or caddy) in front of it.
FABRICATOR_HOST=127.0.0.1
FABRICATOR_PORT=5000
FABRICATOR_ENV=production
EOF
        $SUDO chown root:fabricator "$ENV_FILE"
        $SUDO chmod 0640 "$ENV_FILE"
    fi

    # 5) Install systemd service
    info "Creating systemd service..."

    SERVICE_FILE="/etc/systemd/system/$SERVICE_NAME"

    $SUDO tee "$SERVICE_FILE" >/dev/null <<EOF
[Unit]
Description=Fabricator Minecraft Manager
After=network.target

[Service]
Type=simple
User=$SERVICE_USER
Group=$SERVICE_USER
UMask=0002
WorkingDirectory=$APP_DIR
EnvironmentFile=/etc/fabricator/fabricator.env
ExecStart=$VENV_DIR/bin/python $APP_DIR/run.py
Restart=on-failure
RestartSec=5
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true
ReadWritePaths=/opt/fabricator /var/lib/fabricator /etc/fabricator
CapabilityBoundingSet=

[Install]
WantedBy=multi-user.target
EOF

    info "Reloading systemd and enabling service..."
    $SUDO systemctl daemon-reload
    $SUDO systemctl enable --now "$SERVICE_NAME"

    echo ""
    info "Fabricator service installed and started."
    info "Check status with: $SUDO systemctl status $SERVICE_NAME"
    echo ""
    info "To manage servers from the CLI as your own user, add yourself to the"
    info "'$SERVICE_USER' group so you have write access to server directories:"
    info "  sudo usermod -aG $SERVICE_USER \$USER"
    info "Then log out and back in for the group change to take effect."
}

main "$@"
