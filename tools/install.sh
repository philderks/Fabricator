#!/bin/sh
set -eu

main() {
    # 1) Detect distro (via /etc/os-release)

	OS_FAMILY=""
	PACKAGETYPE=""

    GITHUB_OWNER="philderks"
    GITHUB_REPO="Fabricator"
    INSTALL_DIR="/opt/fabricator"
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
    # 5) Install systemd service
}

main "$@"
