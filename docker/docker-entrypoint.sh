#!/bin/sh
set -e

# A freshly-created named volume (or bind mount) comes up root-owned, so the
# unprivileged 'fabricator' user could not write to /data. Fix ownership of the
# mount root as root on startup (non-recursive: the app creates its subtrees as
# fabricator, and -R would rescan the whole world/backup data on every boot),
# then drop privileges and hand off to tini as PID 1.
#
# Note: migrating a volume previously written by a root-running container needs
# a one-time `chown -R` by hand; fresh deployments need nothing.
if [ "$(id -u)" = "0" ]; then
    mkdir -p /data
    chown fabricator:fabricator /data
    exec gosu fabricator tini -- "$@"
fi

# Already unprivileged (e.g. a compose `user:` override) — just exec.
exec tini -- "$@"
