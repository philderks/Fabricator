"""Pin: the java archive extractor unpacks an ordinary vendor tarball
completely through the shared ``safe_extract_tar`` path.

Regression guard for the #5/#8 sweep that deleted java_manager's hand-rolled
``_safe_extract_tar`` and routed extraction through ``backend.utils.zip``.
"""
from __future__ import annotations

import io
import tarfile

from backend.server.java_manager import _extract_archive


def test_extract_archive_unpacks_ordinary_targz_completely(tmp_path):
    src = tmp_path / "jdk.tar.gz"
    files = {
        "jdk-21/bin/java": b"ELF-ish",
        "jdk-21/lib/modules": b"modules-blob",
        "jdk-21/release": b"JAVA_VERSION=21",
    }
    with tarfile.open(src, "w:gz") as tf:
        for name, data in files.items():
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))

    staging = tmp_path / "staging"
    staging.mkdir()
    _extract_archive(src, staging)

    for name, data in files.items():
        out = staging / name
        assert out.is_file(), f"{name} missing after extraction"
        assert out.read_bytes() == data
