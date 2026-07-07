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

    # playit.gg tunnel agent — pinned to a known-verified release.
    # Bumping this constant requires refreshing every sha256 in PLAYIT_SHA256
    # from https://api.github.com/repos/playit-cloud/playit-agent/releases/tags/<ver>
    # (the per-asset `digest` field).
    PLAYIT_VERSION="v1.0.5"
    declare -A PLAYIT_SHA256=(
        [playit-linux-amd64]=217bd341b3ea88f982ce45bb68aa8b795bf8d6866be841cc675d36f3c6b90277
        [playit-linux-aarch64]=7cfcf151581076295a210d56d2015a4b0b1ef26f4b3d4b753424c5d96eca6d95
        [playit-linux-armv7]=140a8a2b49ee01d0562cd1a2c898dc641d640057c62cf6172724587cdf08828a
        [playit-linux-i686]=c7b84d00aeb2735645230d5d9479a90a6bb2999f679d48613c91def30758580b
        [playit-cli-linux-amd64]=1a3e6f2acfef345dafe32daa280ce4dc62e39601ff083bb5b88ea28ae7e5168c
        [playit-cli-linux-aarch64]=0b7a8d580727a1d2ff249ab96eab5233b7973720f6df245764016f4436d3ff70
        [playit-cli-linux-armv7]=98855142ef50d49cb85b84b61531423ffac11bf78eafa250f43453e9e14cbe1e
        [playit-cli-linux-i686]=571a4e22148e3c6c8a0d90ad3dbf4a7d43e18d1bd40e367cb755a5e355903775
    )
    PLAYIT_BINARY_VERIFIED="false"   # set to "true" only after successful sha256 verify
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
    # $DATA_DIR/update holds the self-update control files: the panel writes
    # `request` (watched by fabricator-update.path); the root oneshot writes
    # `update.log` and `result` back for the panel to read.
    $SUDO mkdir -p "$DATA_DIR" "$DATA_DIR/servers" "$DATA_DIR/update"
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

    # Install pinned playit-agent binaries (daemon + CLI) with sha256 verification.
    # Sets the outer PLAYIT_BINARY_VERIFIED to "true" on full success, "false" otherwise.
    # Never aborts the Fabricator install on failure — playit is optional at runtime.
    install_playit_binaries() {
        local arch_raw arch daemon_asset cli_asset playit_dir
        arch_raw="$(uname -m)"
        case "$arch_raw" in
            x86_64)          arch="amd64"   ;;
            aarch64|arm64)   arch="aarch64" ;;
            armv7l)          arch="armv7"   ;;
            i386|i686)       arch="i686"    ;;
            *)
                warn "playit: unsupported architecture '$arch_raw'; skipping playit binary install."
                return 0
                ;;
        esac
        daemon_asset="playit-linux-${arch}"
        cli_asset="playit-cli-linux-${arch}"

        local daemon_sha cli_sha
        daemon_sha="${PLAYIT_SHA256[$daemon_asset]:-}"
        cli_sha="${PLAYIT_SHA256[$cli_asset]:-}"
        if [[ -z "$daemon_sha" || -z "$cli_sha" ]]; then
            warn "playit: no pinned sha256 for ${arch} in PLAYIT_SHA256; skipping."
            return 0
        fi

        # Drift detection: if both binaries are already present and match the
        # pinned sha256, skip the download entirely. This applies to updates too
        # (the pin only moves when PLAYIT_VERSION is bumped), so a routine update
        # doesn't re-fetch ~unchanged binaries from GitHub every time.
        if [[ -x /usr/local/bin/playit \
              && -x /usr/local/bin/playit-cli ]]; then
            if echo "${daemon_sha}  /usr/local/bin/playit" | sha256sum -c - >/dev/null 2>&1 \
               && echo "${cli_sha}  /usr/local/bin/playit-cli" | sha256sum -c - >/dev/null 2>&1; then
                info "playit ${PLAYIT_VERSION} binaries already present and verified."
                PLAYIT_BINARY_VERIFIED="true"
                return 0
            fi
            info "playit: existing binaries do not match pin; re-downloading."
        fi

        local base="https://github.com/playit-cloud/playit-agent/releases/download/${PLAYIT_VERSION}"
        local tmp
        tmp="$(mktemp -d)"

        info "playit: downloading ${PLAYIT_VERSION} (${arch})..."
        if ! curl -fSL --retry 3 "${base}/${daemon_asset}" -o "${tmp}/${daemon_asset}"; then
            warn "playit: download of ${daemon_asset} failed."
            rm -rf "$tmp"
            return 0
        fi
        if ! curl -fSL --retry 3 "${base}/${cli_asset}" -o "${tmp}/${cli_asset}"; then
            warn "playit: download of ${cli_asset} failed."
            rm -rf "$tmp"
            return 0
        fi

        if ! echo "${daemon_sha}  ${tmp}/${daemon_asset}" | sha256sum -c - >/dev/null 2>&1; then
            warn "playit: sha256 mismatch on ${daemon_asset}; refusing to install."
            rm -rf "$tmp"
            return 0
        fi
        if ! echo "${cli_sha}  ${tmp}/${cli_asset}" | sha256sum -c - >/dev/null 2>&1; then
            warn "playit: sha256 mismatch on ${cli_asset}; refusing to install."
            rm -rf "$tmp"
            return 0
        fi

        $SUDO install -m 0755 -o root -g root "${tmp}/${daemon_asset}" /usr/local/bin/playit
        $SUDO install -m 0755 -o root -g root "${tmp}/${cli_asset}"    /usr/local/bin/playit-cli
        rm -rf "$tmp"

        playit_dir="${DATA_DIR}/playit"
        $SUDO mkdir -p "$playit_dir"
        $SUDO chown "$SERVICE_USER:$SERVICE_USER" "$playit_dir"
        $SUDO chmod 0700 "$playit_dir"

        info "playit ${PLAYIT_VERSION} installed to /usr/local/bin (sha256 verified)."
        PLAYIT_BINARY_VERIFIED="true"
    }

    install_playit_binaries

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

    APP_SRC_DIR="$TMP_DIR/fabricator"

    if [[ -n "${FABRICATOR_LOCAL_SRC:-}" ]]; then
      # Dev/testing escape hatch: deploy from a local checkout instead of a
      # published release asset. Mirrors the CI tarball layout exactly (see
      # .github/workflows/release.yml) so the installed payload matches a real
      # release. Use this to test unreleased branches end-to-end:
      #   sudo FABRICATOR_LOCAL_SRC=/path/to/checkout bash tools/install.sh --update
      # NOTE: the prebuilt frontend/dist is copied as-is — run `npm run build`
      # in frontend/ first if you changed any frontend code.
      local_src="$(cd "$FABRICATOR_LOCAL_SRC" && pwd)"
      info "Local source mode: staging from $local_src (skipping release download)"
      mkdir -p "$APP_SRC_DIR/frontend" "$APP_SRC_DIR/apps"
      rsync -a --exclude='__pycache__/' --exclude='*.pyc' "$local_src/backend/" "$APP_SRC_DIR/backend/"
      rsync -a --exclude='__pycache__/' --exclude='*.pyc' "$local_src/apps/cli/" "$APP_SRC_DIR/apps/cli/"
      rsync -a --exclude='__pycache__/' --exclude='*.pyc' "$local_src/tools/" "$APP_SRC_DIR/tools/"
      cp "$local_src/run.py" "$local_src/requirements.txt" "$local_src/pyproject.toml" "$APP_SRC_DIR/"
      if [[ -d "$local_src/frontend/dist" ]]; then
        cp -r "$local_src/frontend/dist" "$APP_SRC_DIR/frontend/dist"
      else
        warn "frontend/dist not found in local source; the UI will not be served."
        warn "Run 'npm ci && npm run build' in frontend/ to build it."
      fi
      TAG="$(git -C "$local_src" describe --tags --always --dirty 2>/dev/null || echo dev-local)"
      info "Local source version marker: $TAG"
    else
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
    fi

    if [[ ! -d "$APP_SRC_DIR" ]]; then
      error "Could not locate extracted Fabricator sources. Expected: $APP_SRC_DIR"
    fi
    info "Source staged at: $APP_SRC_DIR"

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
    # Reuse an existing venv across updates instead of recreating it: a fresh
    # `python3 -m venv` plus a full dependency reinstall on every update is the
    # main reason an update drags on (and risks the systemd start timeout). When
    # the venv is already there, pip's "already satisfied" fast path skips most
    # of the work and only changed/new requirements are installed.
    if [ -x "$VENV_DIR/bin/python" ]; then
        info "Reusing existing Python virtualenv at $VENV_DIR"
    else
        info "Creating Python virtualenv..."
        run_as_service_user python3 -m venv "$VENV_DIR"
    fi
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

# Self-update: the panel queues updates via a request file watched by
# fabricator-update.path (instead of sudo, which the sandboxed unit forbids).
FABRICATOR_UPDATE_MODE=systemd
FABRICATOR_UPDATE_DIR=${DATA_DIR}/update

# playit.gg tunnel agent — set to "true" to start automatically on boot.
PLAYIT_ENABLED=false
# Reflects whether install.sh verified the pinned playit binary sha256.
# Backend reads this; UI shows a non-blocking warning when "false".
PLAYIT_BINARY_VERIFIED=${PLAYIT_BINARY_VERIFIED}
EOF
        $SUDO chown root:fabricator "$ENV_FILE"
        $SUDO chmod 0640 "$ENV_FILE"
    else
        # Env file already exists (update path). Refresh PLAYIT_BINARY_VERIFIED
        # in place so stale "false" doesn't survive a successful re-verify.
        if $SUDO grep -q '^PLAYIT_BINARY_VERIFIED=' "$ENV_FILE"; then
            $SUDO sed -i "s|^PLAYIT_BINARY_VERIFIED=.*|PLAYIT_BINARY_VERIFIED=${PLAYIT_BINARY_VERIFIED}|" "$ENV_FILE"
        else
            echo "PLAYIT_BINARY_VERIFIED=${PLAYIT_BINARY_VERIFIED}" | $SUDO tee -a "$ENV_FILE" >/dev/null
        fi
        # Backfill self-update settings for installs created before trigger-file
        # updates existed (older installs used the now-removed sudo path).
        if ! $SUDO grep -q '^FABRICATOR_UPDATE_MODE=' "$ENV_FILE"; then
            echo "FABRICATOR_UPDATE_MODE=systemd" | $SUDO tee -a "$ENV_FILE" >/dev/null
        fi
        if ! $SUDO grep -q '^FABRICATOR_UPDATE_DIR=' "$ENV_FILE"; then
            echo "FABRICATOR_UPDATE_DIR=${DATA_DIR}/update" | $SUDO tee -a "$ENV_FILE" >/dev/null
        fi
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

    # In-app self-update: a root oneshot, fired by a path unit watching a file
    # the panel can write. This replaces the old `sudo -n update.sh` design,
    # which could never work: the main service runs NoNewPrivileges=true (so
    # sudo cannot regain root) under ProtectSystem=strict (so even root could
    # not write /etc, /usr). The oneshot runs OUTSIDE that sandbox, and being a
    # separate unit it survives install.sh restarting fabricator.service.
    UPDATE_BASH="$(command -v bash)"
    if [[ -z "$UPDATE_BASH" ]]; then
        error "bash not found; cannot configure self-update."
    fi
    info "Configuring self-update trigger units..."

    UPDATE_REQUEST_FILE="$DATA_DIR/update/request"
    UPDATE_LOG_FILE="$DATA_DIR/update/update.log"
    UPDATE_RESULT_FILE="$DATA_DIR/update/result"

    # Drop the obsolete sudoers rule from pre-trigger installs.
    $SUDO rm -f /etc/sudoers.d/fabricator-self-update

    $SUDO tee "/etc/systemd/system/fabricator-update.service" >/dev/null <<EOF
[Unit]
Description=Fabricator self-update job
# Deliberately unsandboxed: install.sh writes system files (systemd units,
# /usr/local/bin, this very unit) and restarts fabricator.service.

[Service]
Type=oneshot
# A full update recreates the venv and reinstalls every Python dependency
# (and re-downloads playit), which routinely takes minutes on slower hosts
# like a Raspberry Pi. Without this, the oneshot inherits DefaultTimeoutStartSec
# (~90s); systemd would SIGTERM the installer mid-pip and the panel would report
# a "failed" update that was only killed for being slow.
TimeoutStartSec=infinity
# The panel can only write the request file's *contents*; update.sh validates
# them against a strict allowlist before trusting the version string.
Environment=FABRICATOR_UPDATE_REQUEST_FILE=${UPDATE_REQUEST_FILE}
# Start each run clean: truncate the log and drop any stale result. We truncate
# here, NOT via StandardOutput=truncate:, because truncate: re-truncates the
# file on every Exec* open — including ExecStopPost, which runs last and would
# wipe the log ExecStart just wrote. append: below then preserves it.
ExecStartPre=-${UPDATE_BASH} -c ': > ${UPDATE_LOG_FILE}; rm -f ${UPDATE_RESULT_FILE}'
ExecStart=${UPDATE_BASH} ${APP_DIR}/tools/update.sh
# Persist the outcome and clear the request so the path unit can re-arm. Runs on
# success, failure, or kill. NOTE: %% escapes systemd's '%' specifier so bash
# receives a literal "%s"; a bare "%s" is expanded by systemd (to the shell
# path) before bash ever runs, writing garbage into the result file.
ExecStopPost=${UPDATE_BASH} -c 'printf "%%s" "\$EXIT_STATUS" > ${UPDATE_RESULT_FILE}; rm -f ${UPDATE_REQUEST_FILE}'
# World-readable log/result so the unprivileged panel user can read them back.
UMask=0022
StandardOutput=append:${UPDATE_LOG_FILE}
StandardError=append:${UPDATE_LOG_FILE}
EOF

    $SUDO tee "/etc/systemd/system/fabricator-update.path" >/dev/null <<EOF
[Unit]
Description=Watch for Fabricator self-update requests

[Path]
PathExists=${UPDATE_REQUEST_FILE}
Unit=fabricator-update.service

[Install]
WantedBy=multi-user.target
EOF

    info "Reloading systemd and enabling service..."
    $SUDO systemctl daemon-reload
    $SUDO systemctl enable --now "$SERVICE_NAME"
    # Arm the self-update watcher. A stale request file from a previous run
    # would otherwise fire the oneshot immediately on enable.
    $SUDO rm -f "$DATA_DIR/update/request"
    $SUDO systemctl enable --now fabricator-update.path

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
