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
    # Set to 1 by tools/update.sh for in-dashboard updates only.
    FABRICATOR_SKIP_OS_PACKAGES="${FABRICATOR_SKIP_OS_PACKAGES:-0}"
    MODE="${FABRICATOR_MODE:-install}"                  # install | update
    SERVER_INDEX_FILE="${SERVER_INDEX_FILE:-${DATA_DIR}/servers.json}"
    ENV_FILE="/etc/fabricator/fabricator.env"

    if [[ "${1:-}" == "--update" ]]; then
        MODE="update"
        shift
    elif [[ "${1:-}" == "--install" ]]; then
        MODE="install"
        shift
    elif [ -f "$APP_DIR/.fabricator_version" ]; then
        MODE="update"
    else
        MODE="install"
    fi

    case "$MODE" in
        install|update) ;;
        *)
            error "Unsupported mode '$MODE'. Use --install or --update."
            ;;
    esac

    if [ -f "$APP_DIR/.fabricator_version" ]; then
        EXISTING_VERSION="$(cat "$APP_DIR/.fabricator_version")"
        if [[ "$MODE" == "update" ]]; then
            info "Existing Fabricator install detected (version: $EXISTING_VERSION). Running update..."
        else
            info "Existing Fabricator install detected (version: $EXISTING_VERSION). Upgrading..."
        fi
    else
        if [[ "$MODE" == "update" ]]; then
            warn "No existing install detected. Continuing update mode as install-like bootstrap."
        else
            info "No existing install detected. Performing fresh install..."
        fi
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

    check_python_version() {
      local min_major=3
      local min_minor=11

      # Find python3 and get its version
      if ! command -v python3 &>/dev/null; then
        error "Python 3 not found. Please install Python ${min_major}.${min_minor} or newer."
        exit 1
      fi

      local py_major py_minor
      py_major=$(python3 -c "import sys; print(sys.version_info.major)")
      py_minor=$(python3 -c "import sys; print(sys.version_info.minor)")

      if [[ "$py_major" -lt "$min_major" ]] || { [[ "$py_major" -eq "$min_major" ]] && [[ "$py_minor" -lt "$min_minor" ]]; }; then
        warn "Python ${py_major}.${py_minor} detected — Fabricator requires Python ${min_major}.${min_minor}+."
        warn "On Ubuntu 22.04: sudo add-apt-repository ppa:deadsnakes/ppa && sudo apt install python3.11"
        error "Aborting: Python version requirement not met."
      fi

      info "Python ${py_major}.${py_minor} ✓"
    }

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

    check_python_version

    _skip_os_packages=false
    case "$FABRICATOR_SKIP_OS_PACKAGES" in
        1|true|TRUE|yes|YES|on|ON)
            _skip_os_packages=true
            ;;
    esac

    if $_skip_os_packages; then
        if [[ "$MODE" != "update" ]]; then
            error "FABRICATOR_SKIP_OS_PACKAGES is only valid for --update mode (used by tools/update.sh)."
        fi
        info "Skipping OS package install (release-only update)."
        for _need in curl tar rsync python3 grep sed; do
            command -v "$_need" >/dev/null 2>&1 ||
                error "Missing system command '$_need'. Run install.sh --update once as root without FABRICATOR_SKIP_OS_PACKAGES to install deps."
        done
        info "Host tools OK; proceeding without apt/pacman/dnf."
    else
        # 2) Install dependencies
        # NOTE: all package-manager commands redirect stdin from /dev/null so they
        # cannot consume the piped script when invoked via  curl … | bash
        info "Installing dependencies for $OS_FAMILY (pkg: $PACKAGETYPE)..."

        case "$PACKAGETYPE" in
            apt)
                # Java is managed per-server via the in-app Java manager (see /api/java).
                DEPS="python3 python3-venv python3-pip curl ca-certificates grep sed tar rsync"
                $SUDO apt-get update </dev/null
                $SUDO apt-get install -y $DEPS </dev/null
                ;;
            pacman)
                DEPS="python python-pip curl ca-certificates grep sed tar rsync"
                $SUDO pacman -Sy --noconfirm $DEPS </dev/null
                ;;
            dnf)
                DEPS="python3 python3-pip curl ca-certificates grep sed tar rsync"
                $SUDO dnf install -y $DEPS </dev/null
                ;;
            *)
                error "internal error: unknown PACKAGETYPE: $PACKAGETYPE"
                ;;
        esac

        info "Dependencies installed."
    fi

    # Create service user if missing
    info "Ensuring service user '$SERVICE_USER' exists..."
    if ! id "$SERVICE_USER" >/dev/null 2>&1; then
        $SUDO useradd --system --home "$DATA_DIR" --shell /usr/sbin/nologin "$SERVICE_USER"
    fi
    $SUDO mkdir -p "$DATA_DIR" "$DATA_DIR/servers"
    $SUDO chown -R "$SERVICE_USER:$SERVICE_USER" "$DATA_DIR"
    $SUDO chmod 0750 "$DATA_DIR"

    # Helper to run commands as the service user
    run_as_service_user() {
        if [ "$(id -u)" -eq 0 ]; then
            su -s /bin/bash "$SERVICE_USER" -c "export PATH='$PATH'; $(printf '%q ' "$@")"
        else
            $SUDO -u "$SERVICE_USER" --preserve-env=PATH "$@"
        fi
    }

    # 3) Download Fabricator release asset
    info "Downloading Fabricator from GitHub Releases..."
    TMP_DIR="$(mktemp -d)"
    cleanup() { rm -rf "$TMP_DIR"; }
    trap cleanup EXIT

    get_latest_tag() {
      curl -fsSL "https://api.github.com/repos/${FABRICATOR_REPO}/releases/latest" \
        | grep -m1 '"tag_name"' \
        | sed -E 's/.*"tag_name":[[:space:]]*"([^"]+)".*/\1/'
    }

    if [[ "$FABRICATOR_VERSION" == "latest" ]]; then
      TAG="$(get_latest_tag || true)"
      if [[ -z "$TAG" ]]; then
        error "Could not determine latest release tag. GitHub API may be rate-limited. Re-run with: FABRICATOR_VERSION=vX.Y.Z"
      fi
      info "Latest release: $TAG"
    elif [[ "$FABRICATOR_VERSION" == "main" ]]; then
      error "FABRICATOR_VERSION=main is no longer supported. Specify a version tag, e.g. FABRICATOR_VERSION=v0.3.0"
    else
      TAG="$FABRICATOR_VERSION"
      info "Using specified version: $TAG"
    fi

    ASSET_URL="https://github.com/${FABRICATOR_REPO}/releases/download/${TAG}/fabricator-${TAG}.tar.gz"
    info "Fetching: $ASSET_URL"
    curl -fsSL "$ASSET_URL" -o "$TMP_DIR/fabricator.tar.gz"
    tar -xzf "$TMP_DIR/fabricator.tar.gz" -C "$TMP_DIR"

    APP_SRC_DIR="$TMP_DIR/fabricator"
    if [[ ! -d "$APP_SRC_DIR" ]]; then
      error "Could not locate extracted Fabricator sources. Expected: $APP_SRC_DIR"
    fi
    info "Source extracted to: $APP_SRC_DIR"

    backup_update_state() {
        local timestamp backup_dir
        timestamp="$(date +%Y%m%d-%H%M%S)"
        backup_dir="${DATA_DIR}/update-backups/${timestamp}"
        $SUDO mkdir -p "$backup_dir"

        if [[ -f "$SERVER_INDEX_FILE" ]]; then
            $SUDO cp -a "$SERVER_INDEX_FILE" "${backup_dir}/servers.json"
            info "Backed up server index to ${backup_dir}/servers.json"
        fi

        if [[ -f "$APP_DIR/servers.json" ]]; then
            $SUDO cp -a "$APP_DIR/servers.json" "${backup_dir}/servers.appdir.json"
            info "Backed up legacy app-dir server index to ${backup_dir}/servers.appdir.json"
        fi

        if [[ -f "$ENV_FILE" ]]; then
            $SUDO cp -a "$ENV_FILE" "${backup_dir}/fabricator.env"
            info "Backed up env config to ${backup_dir}/fabricator.env"
        fi
    }

    if [[ "$MODE" == "update" ]]; then
        backup_update_state
    fi

    # Sync into install location
    if $SUDO systemctl is-active --quiet "$SERVICE_NAME" 2>/dev/null; then
        info "Stopping running Fabricator service before update..."
        $SUDO systemctl stop "$SERVICE_NAME"
    fi
    $SUDO mkdir -p "$APP_DIR"
    $SUDO rsync -a --delete \
        --exclude .git \
        --exclude servers.json \
        --exclude .fabricator_version \
        "$APP_SRC_DIR/" "$APP_DIR/"
    $SUDO chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR"
    $SUDO chmod -R 755 "$INSTALL_DIR"

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

    # 4b) Install CLI entry point
    if [ -f "$APP_DIR/pyproject.toml" ]; then
        info "Installing Fabricator CLI entry point..."
        run_as_service_user "$VENV_DIR/bin/pip" install -e "$APP_DIR" --break-system-packages </dev/null
        $SUDO ln -sf "$VENV_DIR/bin/fabricator" /usr/local/bin/fabricator
        info "CLI available as: fabricator"
    fi

    # Config
    info "Creating config directory /etc/fabricator..."
    $SUDO mkdir -p /etc/fabricator

    if [ ! -f "$ENV_FILE" ]; then
        info "Creating default env file at $ENV_FILE"
        $SUDO tee "$ENV_FILE" >/dev/null <<EOF
# Fabricator environment configuration
HOST=0.0.0.0
PORT=5000
FLASK_ENV=production
SERVER_ROOT=${DATA_DIR}/servers
SERVER_INDEX_FILE=${DATA_DIR}/servers.json

# playit.gg tunnel agent — set to "true" to start automatically on boot.
PLAYIT_ENABLED=false
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

    # In-app updater runs as $SERVICE_USER; install.sh needs root — grant one NOPASSWD path.
    UPDATE_BASH="$(command -v bash)"
    if [[ -z "$UPDATE_BASH" ]]; then
        error "bash not found; cannot configure self-update."
    fi
    SUDO_DROPIN="/etc/sudoers.d/fabricator-self-update"
    info "Configuring passwordless sudo for dashboard self-update..."
    $SUDO tee "$SUDO_DROPIN" >/dev/null <<EOF
# Managed by Fabricator install.sh — do not edit by hand
${SERVICE_USER} ALL=(root) NOPASSWD: ${UPDATE_BASH} ${APP_DIR}/tools/update.sh, ${UPDATE_BASH} ${APP_DIR}/tools/update.sh *
EOF
    $SUDO chmod 0440 "$SUDO_DROPIN"
    if ! $SUDO visudo -cf "$SUDO_DROPIN" >/dev/null 2>&1; then
        $SUDO rm -f "$SUDO_DROPIN"
        error "sudoers drop-in failed validation and was removed. Please report this to Fabricator."
    fi

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
    echo ""
    info "Java is not installed system-wide. Install JREs per server through the"
    info "Fabricator UI"
    echo ""

    # Dashboard bind address + port (from env; defaults match new installs)
    local DASH_HOST="0.0.0.0" DASH_PORT="5000" _hv _pv URL_HOST=""
    if [ -f "$ENV_FILE" ]; then
        _hv="$($SUDO grep -E '^[[:space:]]*HOST=' "$ENV_FILE" 2>/dev/null | tail -n1 | sed -E 's/^[[:space:]]*HOST=//; s/#.*//; s/[[:space:]]+$//; s/^[\"'\'']//; s/[\"'\'']$//')"
        _pv="$($SUDO grep -E '^[[:space:]]*PORT=' "$ENV_FILE" 2>/dev/null | tail -n1 | sed -E 's/^[[:space:]]*PORT=//; s/#.*//; s/[[:space:]]+$//; s/^[\"'\'']//; s/[\"'\'']$//')"
        [[ -n "$_hv" ]] && DASH_HOST="$_hv"
        [[ -n "$_pv" ]] && DASH_PORT="$_pv"
    fi
    if [[ "$DASH_HOST" == "0.0.0.0" ]] || [[ "$DASH_HOST" == "*" ]] || [[ -z "$DASH_HOST" ]]; then
        URL_HOST="$(hostname -I 2>/dev/null | awk '{print $1}')"
        if [[ -z "$URL_HOST" ]]; then
            URL_HOST="$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for (i = 1; i <= NF; i++) if ($i == "src") { print $(i + 1); exit }}')"
        fi
        info "Dashboard bind: 0.0.0.0 (all interfaces), port: $DASH_PORT"
        if [[ -n "$URL_HOST" ]]; then
            info "Open in a browser: http://${URL_HOST}:${DASH_PORT}/"
        else
            info "Open in a browser: http://<this-host-ip>:${DASH_PORT}/"
        fi
    elif [[ "$DASH_HOST" == "127.0.0.1" ]] || [[ "$DASH_HOST" == "localhost" ]]; then
        info "Dashboard address: $DASH_HOST, port: $DASH_PORT"
        info "Open in a browser: http://127.0.0.1:${DASH_PORT}/"
    else
        URL_HOST="$DASH_HOST"
        info "Dashboard address: $DASH_HOST, port: $DASH_PORT"
        info "Open in a browser: http://${URL_HOST}:${DASH_PORT}/"
    fi
}

main "$@"
