"""Application version source-of-truth.

The release workflow writes the git tag into ``.fabricator_version`` at the
repository root before tarballing. The installer copies that file into
``$APP_DIR/.fabricator_version``. This module centralises the read so callers
do not need to know where the file lives.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import List


def _candidate_paths() -> List[Path]:
    here = Path(__file__).resolve()
    project_root = here.parents[2]
    return [
        Path.cwd() / ".fabricator_version",
        project_root / ".fabricator_version",
    ]


@lru_cache(maxsize=1)
def get_app_version() -> str:
    for candidate in _candidate_paths():
        if not candidate.exists():
            continue
        try:
            value = candidate.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if value:
            return value
    return "unknown"
