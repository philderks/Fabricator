#!/bin/sh
set -eu

main() {
    # 1) Detect distro (via /etc/os-release)

	OS_FAMILY=""
	PACKAGETYPE=""

	if [ -f /etc/os-release ]; then
		# /etc/os-release populates a number of shell variables. We care about the following:
		#  - ID: the short name of the OS (e.g. "debian", "freebsd")
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
    # 3) Download Fabricator release (from GitHub)
    # 4) Install binary to /usr/local/bin
    # 5) Install systemd service
}

main "$@"
