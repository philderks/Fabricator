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


def test_extract_archive_unpacks_temurin_legal_symlinks(tmp_path):
    """Regression for #51: Temurin's Linux/macOS tarballs carry ~200 relative
    symlinks under ``legal/`` (every module's LICENSE points at
    ``../java.base/...``). The extractor used to refuse the first one and abort
    the whole Java install with "Archive member is a link (refusing)"."""
    src = tmp_path / "jdk.tar.gz"
    with tarfile.open(src, "w:gz") as tf:
        license_blob = b"GPLv2 + Classpath"
        info = tarfile.TarInfo(name="jdk-25/legal/java.base/LICENSE")
        info.size = len(license_blob)
        tf.addfile(info, io.BytesIO(license_blob))

        binary = b"ELF-ish"
        info = tarfile.TarInfo(name="jdk-25/bin/java")
        info.size = len(binary)
        info.mode = 0o755
        tf.addfile(info, io.BytesIO(binary))

        for module in ("jdk.jshell", "java.rmi", "jdk.jstatd"):
            link = tarfile.TarInfo(name=f"jdk-25/legal/{module}/LICENSE")
            link.type = tarfile.SYMTYPE
            link.linkname = "../java.base/LICENSE"
            tf.addfile(link)

    staging = tmp_path / "staging"
    staging.mkdir()
    _extract_archive(src, staging)

    for module in ("jdk.jshell", "java.rmi", "jdk.jstatd"):
        link = staging / "jdk-25" / "legal" / module / "LICENSE"
        assert link.is_symlink(), f"{module} LICENSE not materialised"
        assert link.read_bytes() == b"GPLv2 + Classpath"
    # The JDK is unusable if the launcher comes out non-executable.
    assert (staging / "jdk-25" / "bin" / "java").stat().st_mode & 0o111 == 0o111
