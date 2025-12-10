#!/bin/sh
set -eu

main() {
    # 1) Detect distro (via /etc/os-release)

	OS_FAMILY=""
	PACKAGETYPE=""

    GITHUB_OWNER="philderks"
    GITHUB_REPO="Fabricator"
    INSTALL_DIR="/srv/fabricator"
    APP_DIR="$INSTALL_DIR/app"
    VENV_DIR="$INSTALL_DIR/venv"
    SERVICE_USER="fabricator"
    SERVICE_NAME="fabricator.service"
    
    # If you always upload an asset called fabricator.tar.gz to each release,
    # this URL will always point to the latest one:
    RELEASE_ASSET_NAME="fabricator.tar.gz"
    RELEASE_URL="https://github.com/$GITHUB_OWNER/$GITHUB_REPO/releases/latest/download/$RELEASE_ASSET_NAME"


	if [ -f /etc/os-release ]; then
		# /etc/os-release populates a number of shell variables. We care about the following:
		#  - ID: the short name of the OS (e.g. "debian", "arch")
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


    # 2) Install dependencies (java, systemd stuff, etc.)
    echo "Installing dependencies for $OS_FAMILY (pkg: $PACKAGETYPE)..."

    case "$PACKAGETYPE" in
        apt)
            DEPS="python3 python3-venv python3-pip curl ca-certificates"
            sudo apt-get update
            sudo apt-get install -y $DEPS
            ;;
        pacman)
            DEPS="python python-pip curl ca-certificates"
            sudo pacman -Sy --noconfirm $DEPS
            ;;
        dnf)
            DEPS="python3 python3-pip curl ca-certificates"
            sudo dnf install -y $DEPS
            ;;
        *)
            echo "internal error: unknown PACKAGETYPE: $PACKAGETYPE"
            exit 1
            ;;
    esac

    echo "Dependencies installed."

    # 3) Download Fabricator release (from GitHub)
    echo "Downloading Fabricator from GitHub..."
    tmpfile="$(mktemp)"
    curl -L "$RELEASE_URL" -o "$tmpfile"

    echo "Preparing install directory at $INSTALL_DIR..."
    sudo mkdir -p "$APP_DIR"
    sudo rm -rf "$APP_DIR"/*
    sudo tar -xzf "$tmpfile" -C "$APP_DIR" --strip-components=1
    rm -f "$tmpfile"

    echo "Setting ownership..."
    sudo chown -R "$SERVICE_USER":"$SERVICE_USER" "$INSTALL_DIR"

    # 4) Install binary to /usr/local/bin
    echo "▶ Creating Python virtualenv..."

    sudo -u "$SERVICE_USER" python3 -m venv "$VENV_DIR"
    sudo -u "$SERVICE_USER" "$VENV_DIR/bin/pip" install --upgrade pip

    if [ -f "$APP_DIR/requirements.txt" ]; then
        echo "▶ Installing Python requirements..."
        sudo -u "$SERVICE_USER" "$VENV_DIR/bin/pip" install -r "$APP_DIR/requirements.txt"
    else
        echo "⚠ No requirements.txt found in $APP_DIR, skipping pip install."
    fi

        echo "▶ Creating config directory /etc/fabricator..."
    sudo mkdir -p /etc/fabricator

    ENV_FILE="/etc/fabricator/fabricator.env"
    if [ ! -f "$ENV_FILE" ]; then
        echo "▶ Creating default env file at $ENV_FILE"
        sudo tee "$ENV_FILE" >/dev/null <<EOF
# Fabricator environment configuration
FABRICATOR_HOST=127.0.0.1
FABRICATOR_PORT=5000
FABRICATOR_ENV=production
EOF
    fi

    # 5) Install systemd service
    echo "▶ Creating systemd service..."

    SERVICE_FILE="/etc/systemd/system/$SERVICE_NAME"

    sudo tee "$SERVICE_FILE" >/dev/null <<EOF
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

    echo "▶ Reloading systemd and enabling service..."
    sudo systemctl daemon-reload
    sudo systemctl enable --now "$SERVICE_NAME"

    echo "✅ Fabricator service installed and started."
    echo "   Check status with: sudo systemctl status $SERVICE_NAME"

}

main
