#!/bin/sh
set -eu

main() {
    # 1) Detect distro (via /etc/os-release)
    # 2) Install dependencies (java, systemd stuff, etc.)
    # 3) Download Fabricator release (from GitHub)
    # 4) Install binary to /usr/local/bin
    # 5) Install systemd service
}

main "$@"
