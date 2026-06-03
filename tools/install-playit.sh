#!/usr/bin/env bash
set -euo pipefail

# ---------------------------------------------------------------------------
# Fabricator — standalone playit.gg agent installer
#
# The main install.sh deliberately does NOT pull in the playit binary, since
# the tunnel is an opt-in feature. This script provisions just the pieces the
# Fabricator playit integration (app/playit.py) expects at runtime:
#
#   * the playit agent binary at  /usr/bin/playit   (_PLAYIT_BIN)
#   * a writable secret directory  /var/lib/fabricator  for /var/lib/fabricator/playit.toml
#
# Usage:
#   sudo ./tools/install-playit.sh            # install latest agent
#   sudo PLAYIT_VERSION=v1.0.4 ./tools/install-playit.sh
#   sudo ./tools/install-playit.sh --uninstall
#
# Binaries come from the official playit-cloud/playit-agent GitHub releases.
# Debian/Ubuntu users may prefer the official apt repo instead; see:
#   https://github.com/playit-cloud/playit-agent#installing-on-ubuntu-or-debian
# ---------------------------------------------------------------------------

main() {
    info()  { echo "[INFO]  $*"; }
    warn()  { echo "[WARN]  $*" >&2; }
    error() { echo "[ERROR] $*" >&2; exit 1; }

    # Keep these in sync with the constants in app/playit.py.
    PLAYIT_BIN="/usr/bin/playit"
    DATA_DIR="/var/lib/fabricator"
    SECRET_FILE="${DATA_DIR}/playit.toml"
    SERVICE_USER="fabricator"

    GH_REPO="playit-cloud/playit-agent"
    PLAYIT_VERSION="${PLAYIT_VERSION:-latest}"   # latest | vX.Y.Z

    ACTION="install"
    if [[ "${1:-}" == "--uninstall" ]]; then
        ACTION="uninstall"
        shift
    elif [[ "${1:-}" == "--install" ]]; then
        shift
    fi

    # --- root/sudo detection (mirrors install.sh) ---
    SUDO=""
    if [ "$(id -u)" -ne 0 ]; then
        if command -v sudo >/dev/null 2>&1; then
            SUDO="sudo"
        else
            warn "This installer needs root privileges (sudo not found)."
            error "Re-run as root or install sudo."
        fi
    fi

    if [[ "$ACTION" == "uninstall" ]]; then
        info "Removing playit agent binary at $PLAYIT_BIN..."
        $SUDO rm -f "$PLAYIT_BIN"
        warn "Leaving secret file $SECRET_FILE in place (delete manually to fully unlink the tunnel)."
        info "playit agent uninstalled. Set PLAYIT_ENABLED=false in /etc/fabricator/fabricator.env and restart fabricator.service."
        return
    fi

    if ! command -v curl >/dev/null 2>&1; then
        error "curl is required to download the playit agent."
    fi

    # --- map machine architecture to the published asset name ---
    local arch asset
    arch="$(uname -m)"
    case "$arch" in
        x86_64|amd64)        asset="playit-linux-amd64"   ;;
        aarch64|arm64)       asset="playit-linux-aarch64" ;;
        armv7l|armv7|armhf)  asset="playit-linux-armv7"   ;;
        i686|i386)           asset="playit-linux-i686"    ;;
        *)
            error "Unsupported CPU architecture '$arch'. Supported: x86_64, aarch64, armv7, i686."
            ;;
    esac

    # --- resolve the download URL ---
    local url
    if [[ "$PLAYIT_VERSION" == "latest" ]]; then
        url="https://github.com/${GH_REPO}/releases/latest/download/${asset}"
        info "Installing latest playit agent ($asset)..."
    else
        url="https://github.com/${GH_REPO}/releases/download/${PLAYIT_VERSION}/${asset}"
        info "Installing playit agent ${PLAYIT_VERSION} ($asset)..."
    fi

    local tmp
    tmp="$(mktemp)"
    cleanup() { rm -f "$tmp"; }
    trap cleanup EXIT

    info "Downloading: $url"
    if ! curl -fsSL "$url" -o "$tmp"; then
        error "Download failed. Check the version tag and your network, then retry."
    fi

    # Sanity check: a successful binary download should be more than a stray
    # error page. Anything under ~1 MiB is almost certainly not the agent.
    local size
    size="$(wc -c < "$tmp")"
    if [[ "$size" -lt 1000000 ]]; then
        error "Downloaded file is only ${size} bytes — likely not the playit binary (bad version tag?)."
    fi

    info "Installing binary to $PLAYIT_BIN..."
    $SUDO install -m 0755 "$tmp" "$PLAYIT_BIN"

    # Verify it actually runs on this host.
    if "$PLAYIT_BIN" --version >/dev/null 2>&1; then
        info "playit installed: $("$PLAYIT_BIN" --version 2>/dev/null | head -n1)"
    else
        warn "Installed $PLAYIT_BIN but '--version' did not succeed; the binary may be incompatible with this host."
    fi

    # Ensure the secret directory exists and is writable by the service user so
    # the agent can persist its claim secret across restarts.
    info "Ensuring secret directory $DATA_DIR exists..."
    $SUDO mkdir -p "$DATA_DIR"
    if id "$SERVICE_USER" >/dev/null 2>&1; then
        $SUDO chown "$SERVICE_USER:$SERVICE_USER" "$DATA_DIR"
    else
        warn "Service user '$SERVICE_USER' not found — run tools/install.sh first so the agent can write $SECRET_FILE."
    fi

    echo ""
    info "playit agent ready."
    info "Enable the tunnel by setting PLAYIT_ENABLED=true in /etc/fabricator/fabricator.env"
    info "then restart the service:  $SUDO systemctl restart fabricator.service"
    info "Or toggle it at runtime from the dashboard: Server → Settings → Network."
}

main "$@"
