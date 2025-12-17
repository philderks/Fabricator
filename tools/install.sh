#!/usr/bin/env bash
set -euo pipefail

main() {
    OS_FAMILY=""
    PACKAGETYPE=""

    GITHUB_OWNER="philderks"
    GITHUB_REPO="Fabricator"
    INSTALL_DIR="/srv/fabricator"
    APP_DIR="$INSTALL_DIR/app"
    VENV_DIR="$INSTALL_DIR/venv"
    SERVICE_USER="fabricator"
    SERVICE_NAME="fabricator.service"

    FABRICATOR_REPO="${FABRICATOR_REPO:-${GITHUB_OWNER}/${GITHUB_REPO}}"
    FABRICATOR_BRANCH="${FABRICATOR_BRANCH:-main}"
    FABRICATOR_VERSION="${FABRICATOR_VERSION:-latest}"  # latest | main | v1.2.3
    APP_SUBDIR="${APP_SUBDIR:-}"                        # e.g. "backend" if run.py lives there

    # --- root/sudo detection ---
    SUDO=""
    if [ "$(id -u)" -ne 0 ]; then
        if command -v sudo >/dev/null 2>&1; then
            SUDO="sudo"
        else
            echo "This installer needs root privileges (sudo not found)."
            echo "Re-run as root or install sudo."
            exit 1
        fi
    fi

    # --- basic tool checks ---
    if ! command -v curl >/dev/null 2>&1; then
        echo "curl is required to download Fabricator."
        exit 1
    fi
    if ! command -v systemctl >/dev/null 2>&1; then
        echo "systemctl not found. This installer currently requires systemd."
        exit 1
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
        echo "Unsupported or unknown Linux distro (ID=${ID:-unknown})."
        echo "Supported so far: Debian/Ubuntu, Arch, Fedora-family."
        exit 1
    fi

    # 2) Install dependencies
    echo "Installing dependencies for $OS_FAMILY (pkg: $PACKAGETYPE)..."

    case "$PACKAGETYPE" in
        apt)
            DEPS="python3 python3-venv python3-pip openjdk-17-jre curl ca-certificates grep sed tar rsync"
            $SUDO apt-get update
            $SUDO apt-get install -y $DEPS
            ;;
        pacman)
            DEPS="python python-pip jre-openjdk curl ca-certificates grep sed tar rsync"
            $SUDO pacman -Sy --noconfirm $DEPS
            ;;
        dnf)
            DEPS="python3 python3-pip java-17-openjdk curl ca-certificates grep sed tar rsync"
            $SUDO dnf install -y $DEPS
            ;;
        *)
            echo "internal error: unknown PACKAGETYPE: $PACKAGETYPE"
            exit 1
            ;;
    esac

    echo "Dependencies installed."

    # Create service user if missing
    echo "Ensuring service user '$SERVICE_USER' exists..."
    if ! id "$SERVICE_USER" >/dev/null 2>&1; then
        $SUDO useradd --system --home "$INSTALL_DIR" --shell /usr/sbin/nologin "$SERVICE_USER"
    fi

    # 3) Download Fabricator sources
    echo "Downloading Fabricator from GitHub..."
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

      echo "Fetching: $url"
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

      if [[ -n "$TAG" ]]; then
        echo "Latest release tag: $TAG"
        download_tarball "tags" "$TAG"
      else
        echo "No releases found (or API blocked). Falling back to branch: ${FABRICATOR_BRANCH}"
        download_tarball "heads" "$FABRICATOR_BRANCH"
      fi
    fi

    SRC_DIR="$(find "$TMP_DIR" -maxdepth 1 -type d -name 'Fabricator-*' | head -n1)"
    if [[ -z "${SRC_DIR:-}" || ! -d "$SRC_DIR" ]]; then
      echo "ERROR: Could not locate extracted Fabricator sources."
      exit 1
    fi

    echo "Source extracted to: $SRC_DIR"

    # Select app subdirectory if needed
    APP_SRC_DIR="$SRC_DIR"
    if [[ -n "$APP_SUBDIR" ]]; then
      APP_SRC_DIR="$SRC_DIR/$APP_SUBDIR"
    fi

    if [[ ! -d "$APP_SRC_DIR" ]]; then
      echo "ERROR: App source directory not found: $APP_SRC_DIR"
      echo "Hint: set APP_SUBDIR (e.g. APP_SUBDIR=backend) if your run.py is not at repo root."
      exit 1
    fi

    # Sync into install location
    $SUDO mkdir -p "$APP_DIR"
    $SUDO rsync -a --delete "$APP_SRC_DIR/" "$APP_DIR/"
    $SUDO chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR"

    # Sanity check
    if [[ ! -f "$APP_DIR/run.py" ]]; then
      echo "ERROR: $APP_DIR/run.py not found after sync."
      echo "Your app may live in a subfolder. Re-run with: APP_SUBDIR=<folder>"
      exit 1
    fi

    # 4) Setup Python venv + requirements
    echo "Creating Python virtualenv..."
    $SUDO -u "$SERVICE_USER" python3 -m venv "$VENV_DIR"
    $SUDO -u "$SERVICE_USER" "$VENV_DIR/bin/pip" install --upgrade pip

    if [ -f "$APP_DIR/requirements.txt" ]; then
        echo "Installing Python requirements..."
        $SUDO -u "$SERVICE_USER" "$VENV_DIR/bin/pip" install -r "$APP_DIR/requirements.txt"
    else
        echo "No requirements.txt found in $APP_DIR, skipping pip install."
    fi

    # Config
    echo "Creating config directory /etc/fabricator..."
    $SUDO mkdir -p /etc/fabricator

    ENV_FILE="/etc/fabricator/fabricator.env"
    if [ ! -f "$ENV_FILE" ]; then
        echo "Creating default env file at $ENV_FILE"
        $SUDO tee "$ENV_FILE" >/dev/null <<EOF
# Fabricator environment configuration
FABRICATOR_HOST=127.0.0.1
FABRICATOR_PORT=5000
FABRICATOR_ENV=production
EOF
        $SUDO chmod 0640 "$ENV_FILE" || true
    fi

    # 5) Install systemd service
    echo "Creating systemd service..."

    SERVICE_FILE="/etc/systemd/system/$SERVICE_NAME"

    $SUDO tee "$SERVICE_FILE" >/dev/null <<EOF
[Unit]
Description=Fabricator Minecraft Manager
After=network.target

[Service]
Type=simple
User=$SERVICE_USER
Group=$SERVICE_USER
WorkingDirectory=$APP_DIR
EnvironmentFile=/etc/fabricator/fabricator.env
ExecStart=$VENV_DIR/bin/python $APP_DIR/run.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

    echo "Reloading systemd and enabling service..."
    $SUDO systemctl daemon-reload
    $SUDO systemctl enable --now "$SERVICE_NAME"

    echo "Fabricator service installed and started."
    echo "Check status with: $SUDO systemctl status $SERVICE_NAME"
}

main "$@"
