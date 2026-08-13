"""Console entry point.

``argv`` is accepted and ignored on purpose: every setting arrives through the
environment (see ``config``), so there is no flag that could put a token on a
command line.
"""
from __future__ import annotations

import sys
from typing import Sequence

from fabricator_mcp.config import ConfigError, PanelConfig

EXIT_CONFIG_ERROR = 2


def main(argv: "Sequence[str] | None" = None) -> int:
    try:
        config = PanelConfig.from_env()
    except ConfigError as exc:
        print(f"fabricator-mcp: {exc}", file=sys.stderr)
        return EXIT_CONFIG_ERROR

    from fabricator_mcp.server import run

    run(config)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
