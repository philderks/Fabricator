"""``python -m backend.auth hash`` — generate a password hash for the env var.

Works wherever ``backend`` is importable (Docker image, source checkout). The
systemd install also exposes this as ``fabricator hash-password``.
"""
from __future__ import annotations

import getpass
import sys

from backend.auth.service import hash_password


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] != "hash":
        print("usage: python -m backend.auth hash", file=sys.stderr)
        return 2
    password = getpass.getpass("Password: ")
    confirm = getpass.getpass("Confirm password: ")
    if not password:
        print("Password must not be empty.", file=sys.stderr)
        return 1
    if password != confirm:
        print("Passwords do not match.", file=sys.stderr)
        return 1
    print(hash_password(password))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
