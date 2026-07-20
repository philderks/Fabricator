"""LaunchSpec dataclass + InstallResult serialization."""
from __future__ import annotations

import hashlib
import re
from unittest.mock import MagicMock

import pytest
import requests

from backend.server.installer.base import (
    HashVerifyError,
    InstallerBase,
    InstallResult,
    InstallStatus,
    LaunchSpec,
    SubprocessTimeout,
    validate_version_token,
    download_with_hash_verify,
    request_with_retry,
    run_subprocess_streaming,
)


def test_launch_spec_to_dict_jar_type():
    spec = LaunchSpec(
        type="jar",
        jar="server.jar",
        jvm_args=[],
        program_args=["nogui"],
    )
    assert spec.to_dict() == {
        "type": "jar",
        "jar": "server.jar",
        "jvm_args": [],
        "program_args": ["nogui"],
        "args_file": None,
    }


def test_launch_spec_to_dict_copies_lists():
    """to_dict must not return references to the dataclass's internal lists."""
    jvm = ["-Dfoo=bar"]
    spec = LaunchSpec(type="jar", jar="server.jar", jvm_args=jvm, program_args=[])
    out = spec.to_dict()
    out["jvm_args"].append("MUTATED")
    assert spec.jvm_args == ["-Dfoo=bar"]


def test_install_result_to_dict_includes_launch():
    spec = LaunchSpec(
        type="jar",
        jar="server.jar",
        jvm_args=[],
        program_args=["nogui"],
    )
    result = InstallResult(
        success=True,
        status=InstallStatus.COMPLETED,
        message="ok",
        launch=spec,
    )
    payload = result.to_dict()
    assert payload["launch"] == {
        "type": "jar",
        "jar": "server.jar",
        "jvm_args": [],
        "program_args": ["nogui"],
        "args_file": None,
    }


def test_install_result_to_dict_launch_none_when_missing():
    result = InstallResult(
        success=False,
        status=InstallStatus.FAILED,
        message="boom",
    )
    assert result.to_dict()["launch"] is None


def test_fabric_installer_returns_launch_spec(tmp_path, monkeypatch):
    """Successful Fabric install returns a jar-type LaunchSpec."""
    from backend.server.installer.fabric import FabricInstaller

    inst = FabricInstaller(tmp_path)

    monkeypatch.setattr(inst, "_get_latest_loader_version", lambda mc: "0.16.0")
    monkeypatch.setattr(inst, "_get_latest_installer_version", lambda: "1.0.0")
    fake_jar = tmp_path / "server.jar"
    fake_jar.write_bytes(b"PK\x03\x04")
    monkeypatch.setattr(
        inst, "_download_server_jar", lambda mc, lv, iv, **kw: fake_jar
    )

    result = inst.install("1.21.4")

    assert result.success is True
    assert result.launch is not None
    assert result.launch.type == "jar"
    assert result.launch.jar == "server.jar"
    assert result.launch.program_args == ["nogui"]
    assert result.launch.jvm_args == []


def test_launch_spec_to_dict_args_file_type():
    spec = LaunchSpec(
        type="args_file",
        args_file="libraries/net/neoforged/neoforge/21.1.228/unix_args.txt",
        jvm_args=[],
        program_args=["nogui"],
    )
    assert spec.to_dict() == {
        "type": "args_file",
        "jar": None,
        "jvm_args": [],
        "program_args": ["nogui"],
        "args_file": "libraries/net/neoforged/neoforge/21.1.228/unix_args.txt",
    }


def test_launch_spec_to_dict_jar_type_includes_null_args_file():
    """Existing jar-type specs must include args_file=None in their dict form."""
    spec = LaunchSpec(
        type="jar",
        jar="server.jar",
        jvm_args=[],
        program_args=["nogui"],
    )
    assert spec.to_dict()["args_file"] is None


def test_installer_base_requires_java_for_install_default_false(tmp_path):
    from backend.server.installer.fabric import FabricInstaller
    assert FabricInstaller(tmp_path).requires_java_for_install is False


def test_vanilla_installer_requires_java_for_install_default_false(tmp_path):
    from backend.server.installer.vanilla import VanillaInstaller
    assert VanillaInstaller(tmp_path).requires_java_for_install is False


def test_installer_base_java_exec_default_none(tmp_path):
    from backend.server.installer.fabric import FabricInstaller
    inst = FabricInstaller(tmp_path)
    assert inst.java_exec is None


def test_installer_base_set_java_exec_records_path(tmp_path):
    from backend.server.installer.fabric import FabricInstaller
    inst = FabricInstaller(tmp_path)
    inst.set_java_exec("/var/lib/fabricator/java/jdk-21/bin/java")
    assert inst.java_exec == "/var/lib/fabricator/java/jdk-21/bin/java"


def test_installer_base_set_java_exec_accepts_none(tmp_path):
    """Clearing the Java path is supported — unsets any prior value."""
    from backend.server.installer.fabric import FabricInstaller
    inst = FabricInstaller(tmp_path)
    inst.set_java_exec("/path/to/java")
    inst.set_java_exec(None)
    assert inst.java_exec is None


# ---------- Canonical MC version form ----------
#
# Modrinth and other downstream consumers tag x.y.0 MC releases with the
# bare "x.y" form. Loaders whose own APIs return the explicit "x.y.0"
# form (notably NeoForge) must canonicalize before returning so all
# loaders surface the same form. These tests pin that invariant.


_X_Y_ZERO_RE = re.compile(r"^[a-z]?\d+\.\d+\.0$")


@pytest.mark.parametrize("raw,expected", [
    ("1.21.0", "1.21"),
    ("1.20.1", "1.20.1"),
    ("1.21", "1.21"),
    ("a1.2.0", "a1.2"),
    ("26.2-snapshot-6", "26.2-snapshot-6"),
])
def test_canonicalize_mc_version(raw, expected):
    assert InstallerBase._canonicalize_mc_version(raw) == expected


def _assert_no_zero_patch(versions):
    offenders = [v["version"] for v in versions if _X_Y_ZERO_RE.match(v.get("version", ""))]
    assert offenders == [], f"x.y.0 entries leaked from get_minecraft_versions: {offenders}"


def test_vanilla_get_minecraft_versions_no_zero_patch(tmp_path):
    """Vanilla legacy entries like 'a1.2.0' must canonicalize before surfacing."""
    from backend.server.installer.vanilla import VanillaInstaller
    inst = VanillaInstaller(tmp_path)

    session = MagicMock()
    manifest = {
        "latest": {"release": "1.21.4", "snapshot": "24w45a"},
        "versions": [
            {"id": "1.21.4", "type": "release", "url": "x"},
            {"id": "1.21.0", "type": "release", "url": "x"},
            {"id": "a1.2.0", "type": "old_alpha", "url": "x"},
        ],
    }

    def get(url, **_):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = manifest
        return resp

    session.get.side_effect = get
    inst.session = session

    _assert_no_zero_patch(inst.get_minecraft_versions())


def test_fabric_get_minecraft_versions_no_zero_patch(tmp_path):
    from backend.server.installer.fabric import FabricInstaller
    inst = FabricInstaller(tmp_path)

    session = MagicMock()
    payload = [
        {"version": "1.21.4", "stable": True},
        {"version": "1.21.0", "stable": True},
        {"version": "1.21", "stable": True},
    ]

    def get(url, **_):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = payload
        return resp

    session.get.side_effect = get
    inst.session = session

    _assert_no_zero_patch(inst.get_minecraft_versions())


def test_quilt_get_minecraft_versions_no_zero_patch(tmp_path):
    from backend.server.installer.quilt import QuiltInstaller
    inst = QuiltInstaller(tmp_path)

    session = MagicMock()
    payload = [
        {"version": "1.21.4", "stable": True},
        {"version": "1.21.0", "stable": True},
    ]

    def get(url, **_):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = payload
        return resp

    session.get.side_effect = get
    inst.session = session

    _assert_no_zero_patch(inst.get_minecraft_versions())


def test_forge_get_minecraft_versions_no_zero_patch(tmp_path):
    """Forge promotions has a few legacy x.y.0 entries (e.g. 1.4.0)."""
    from backend.server.installer.forge import ForgeInstaller
    inst = ForgeInstaller(tmp_path)

    session = MagicMock()
    promotions = {
        "promos": {
            "1.21.4-latest": "54.1.16",
            "1.4.0-latest": "6.0.0.0",
            "1.20.1-recommended": "47.4.10",
        },
    }

    def get(url, **_):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = promotions
        return resp

    session.get.side_effect = get
    inst.session = session

    _assert_no_zero_patch(inst.get_minecraft_versions())


def test_neoforge_get_minecraft_versions_no_zero_patch(tmp_path):
    """The bug fix: NeoForge's 21.0.x → MC 1.21.0 must canonicalize to '1.21'."""
    from backend.server.installer.neoforge import NeoForgeInstaller
    inst = NeoForgeInstaller(tmp_path)

    session = MagicMock()
    payload = {
        "isSnapshot": False,
        "versions": ["21.0.143", "21.1.228", "26.1.2.43-beta"],
    }

    def get(url, **_):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = payload
        return resp

    session.get.side_effect = get
    inst.session = session

    _assert_no_zero_patch(inst.get_minecraft_versions())


# ---------- B10 Path-traversal mitigation (S1 + S5) ----------
#
# These tests pin the trust-boundary contract that closes Sicherheits-Block
# S1 (Forge mc_version/build) and S5 (NeoForge / Quilt loader_version /
# install-dir): every externally-controlled version token is whitelisted by
# ``validate_version_token`` before it lands in a filename or subprocess
# arg, and every path constructed from those tokens is re-checked under
# ``install_path`` by ``_resolve_within_install_path``.


@pytest.mark.parametrize("good", [
    "1.20.1",
    "1.21",
    "b1.7.3",
    "21.1.228",
    "54.1.16",
    "1.21.4-rc1",
    "0.27.0",
    "26.1.2.43-beta",
    "10.13.4.1614",
])
def test_validate_version_token_accepts_real_version_shapes(good):
    assert validate_version_token(good, field_name="mc_version") == good


@pytest.mark.parametrize("bad", [
    "../../etc/passwd",
    "..",
    "../1.20.1",
    "1.20.1/..",
    "1.20.1 --evil",
    "1.20.1\nrm -rf /",
    "1.20.1; rm -rf /",
    "1.20.1\\..",
    "",
    "1.20.1\x00",
    "1.20.1/extra",
    # B15.5b: length-cap {1,128} — 129-char input must be rejected even when
    # every char individually matches [A-Za-z0-9._+\-].
    "1." + "a" * 127,
])
def test_validate_version_token_rejects_path_and_shell_metachars(bad):
    with pytest.raises(ValueError, match="Invalid mc_version"):
        validate_version_token(bad, field_name="mc_version")


def test_validate_version_token_rejects_non_string():
    with pytest.raises(ValueError, match="Invalid build"):
        validate_version_token(None, field_name="build")  # type: ignore[arg-type]


def test_validate_version_token_field_name_in_error_message():
    """Error must name the field so install routes can log a clear failure."""
    with pytest.raises(ValueError, match="loader_version"):
        validate_version_token("..", field_name="loader_version")


def test_resolve_within_install_path_returns_resolved_descendant(tmp_path):
    from backend.server.installer.fabric import FabricInstaller
    inst = FabricInstaller(tmp_path)

    out = inst._resolve_within_install_path("forge-1.20.1-47.4.10-installer.jar")
    assert out == (tmp_path / "forge-1.20.1-47.4.10-installer.jar").resolve()
    # Result is always under the install path.
    assert out.is_relative_to(tmp_path.resolve())


def test_resolve_within_install_path_accepts_nested_segments(tmp_path):
    from backend.server.installer.fabric import FabricInstaller
    inst = FabricInstaller(tmp_path)

    out = inst._resolve_within_install_path(
        "libraries", "net", "neoforged", "neoforge", "21.1.228", "unix_args.txt"
    )
    expected = (
        tmp_path / "libraries" / "net" / "neoforged" / "neoforge"
        / "21.1.228" / "unix_args.txt"
    ).resolve()
    assert out == expected


def test_resolve_within_install_path_rejects_parent_traversal(tmp_path):
    from backend.server.installer.fabric import FabricInstaller
    inst = FabricInstaller(tmp_path)

    with pytest.raises(ValueError, match="escapes install_path"):
        inst._resolve_within_install_path("..", "etc", "passwd")


def test_resolve_within_install_path_rejects_absolute_segment(tmp_path):
    """An absolute path part replaces the prior parts under pathlib semantics."""
    from backend.server.installer.fabric import FabricInstaller
    inst = FabricInstaller(tmp_path)

    with pytest.raises(ValueError, match="escapes install_path"):
        inst._resolve_within_install_path("/etc/passwd")


def test_resolve_within_install_path_rejects_sibling_prefix(tmp_path):
    """A sibling dir whose name is a prefix of install_path must not pass."""
    from backend.server.installer.fabric import FabricInstaller
    sibling = tmp_path / "sibling"
    sibling.mkdir()
    inst = FabricInstaller(sibling)

    with pytest.raises(ValueError, match="escapes install_path"):
        # ../sibling-evil-suffix would resolve to a path that *starts* with
        # str(sibling) but isn't under it. relative_to() catches this.
        inst._resolve_within_install_path("..", "sibling-evil-suffix")


def test_resolve_within_install_path_zero_parts_returns_install_root(tmp_path):
    """Calling with no parts returns the resolved install_path itself."""
    from backend.server.installer.fabric import FabricInstaller
    inst = FabricInstaller(tmp_path)

    out = inst._resolve_within_install_path()
    assert out == tmp_path.resolve()


# ---------- B11 download_with_hash_verify (S7 Sicherheits-Block) ----------
#
# Helper consolidates the streaming + hash-verify dance previously copied
# across vanilla/neoforge/quilt + the modrinth client. Lazy-init: only the
# requested algos run. Mismatch unlinks the partial file and raises
# HashVerifyError; network/OSError unlink and re-raise the original.


def _stub_session(payload: bytes) -> MagicMock:
    """Return a MagicMock session whose .get streams ``payload`` in chunks."""
    session = MagicMock()
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.headers = {"Content-Length": str(len(payload))}
    response.iter_content = lambda chunk_size: iter([payload])
    response.__enter__ = lambda self: self
    response.__exit__ = lambda *a: False
    session.get = MagicMock(return_value=response)
    return session


def test_download_with_hash_verify_happy_path_sha1(tmp_path):
    payload = b"hello world"
    expected = hashlib.sha1(payload).hexdigest()
    target = tmp_path / "out.bin"
    session = _stub_session(payload)

    download_with_hash_verify(
        "https://example.invalid/x", target, sha1=expected, session=session
    )

    assert target.read_bytes() == payload


def test_download_with_hash_verify_happy_path_sha512(tmp_path):
    payload = b"hello world"
    expected = hashlib.sha512(payload).hexdigest()
    target = tmp_path / "out.bin"
    session = _stub_session(payload)

    download_with_hash_verify(
        "https://example.invalid/x", target, sha512=expected, session=session
    )

    assert target.read_bytes() == payload


def test_download_with_hash_verify_happy_path_sha256(tmp_path):
    payload = b"hello world"
    expected = hashlib.sha256(payload).hexdigest()
    target = tmp_path / "out.bin"
    session = _stub_session(payload)

    download_with_hash_verify(
        "https://example.invalid/x", target, sha256=expected, session=session
    )

    assert target.read_bytes() == payload


def test_download_with_hash_verify_sha256_mismatch_unlinks(tmp_path):
    payload = b"hello world"
    target = tmp_path / "out.bin"
    session = _stub_session(payload)

    with pytest.raises(HashVerifyError):
        download_with_hash_verify(
            "https://example.invalid/x",
            target,
            sha256="00" * 32,  # 64 hex, wrong
            session=session,
        )
    assert not target.exists()


def test_download_with_hash_verify_handles_missing_content_length(tmp_path):
    """Chunked transfer encoding (no ``Content-Length``) is non-fatal.

    Behaviour pinned: the response omits ``Content-Length`` so ``bytes_total``
    falls back to ``0``. The download still completes; the progress callback
    is invoked with ``(bytes_done, 0)`` where ``bytes_done`` may exceed the
    reported total. Pre-B11 inline code tolerated this — the helper does too.
    """
    payload = b"chunked-stream-payload"
    target = tmp_path / "chunked.bin"

    session = MagicMock()
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.headers = {}  # no Content-Length → chunked encoding contract
    response.iter_content = lambda chunk_size: iter([payload])
    response.__enter__ = lambda self: self
    response.__exit__ = lambda *a: False
    session.get = MagicMock(return_value=response)

    events: list[tuple[int, int]] = []

    download_with_hash_verify(
        "https://example.invalid/chunked",
        target,
        session=session,
        progress_callback=lambda done, total: events.append((done, total)),
    )

    assert target.read_bytes() == payload
    # At least one callback invocation, all with bytes_total == 0.
    assert events, "progress_callback was never invoked"
    assert all(total == 0 for _, total in events)
    # bytes_done exceeds the reported total (0) — this is the contract under
    # chunked encoding and the helper does not error on it.
    assert events[-1][0] == len(payload)


def test_download_with_hash_verify_size_mismatch_no_hash_path(tmp_path):
    """No hash + Content-Length mismatch → HashVerifyError, target unlinked.

    Fabric Meta serves the server JAR without an upstream hash. The
    Content-Length size-check is the Best-Effort tamper-detection that
    closes the no-hash gap (B15.5b). Mismatch must NOT leak partial bytes
    to ``target``.
    """
    payload = b"truncated-payload"
    target = tmp_path / "fabric.jar"

    session = MagicMock()
    response = MagicMock()
    response.raise_for_status = MagicMock()
    # Server claims 100 bytes via Content-Length; we only stream `payload`.
    response.headers = {"Content-Length": "100"}
    response.iter_content = lambda chunk_size: iter([payload])
    response.__enter__ = lambda self: self
    response.__exit__ = lambda *a: False
    session.get = MagicMock(return_value=response)

    with pytest.raises(HashVerifyError, match="Size mismatch"):
        download_with_hash_verify(
            "https://example.invalid/fabric.jar", target, session=session
        )

    assert not target.exists(), "target must be unlinked on size mismatch"


def test_download_with_hash_verify_no_hash_chunked_logs_warning(tmp_path, caplog):
    """No hash + no Content-Length (chunked) → WARN log, accept.

    Documented limitation: when the server uses chunked transfer encoding
    AND no upstream hash is available, body integrity cannot be verified.
    The download is accepted (legacy behaviour) but a WARN log surfaces
    the gap.
    """
    import logging
    payload = b"chunked-fabric-payload"
    target = tmp_path / "fabric.jar"

    session = MagicMock()
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.headers = {}  # no Content-Length → bytes_total=0
    response.iter_content = lambda chunk_size: iter([payload])
    response.__enter__ = lambda self: self
    response.__exit__ = lambda *a: False
    session.get = MagicMock(return_value=response)

    with caplog.at_level(logging.WARNING, logger="backend.server.installer.base"):
        download_with_hash_verify(
            "https://example.invalid/fabric.jar", target, session=session
        )

    assert target.read_bytes() == payload
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert any("size cannot be verified" in r.getMessage() for r in warnings), (
        f"Expected size-cannot-be-verified WARN, got: {[r.getMessage() for r in warnings]}"
    )


def test_download_with_hash_verify_no_hash_pass_through(tmp_path):
    """Both sha1 and sha512 None → bytes are still written (no integrity gate)."""
    payload = b"\x00\x01\x02"
    target = tmp_path / "raw.bin"
    session = _stub_session(payload)

    download_with_hash_verify("https://example.invalid/x", target, session=session)

    assert target.read_bytes() == payload


def test_download_with_hash_verify_sha1_mismatch_unlinks_and_raises(tmp_path):
    payload = b"hello world"
    bad_sha1 = "deadbeef" * 5  # 40 hex chars, intentionally wrong
    target = tmp_path / "evil.bin"
    session = _stub_session(payload)

    with pytest.raises(HashVerifyError, match="SHA1"):
        download_with_hash_verify(
            "https://example.invalid/x", target, sha1=bad_sha1, session=session
        )

    assert not target.exists()


def test_download_with_hash_verify_sha512_mismatch_unlinks_and_raises(tmp_path):
    payload = b"hello world"
    bad_sha512 = "deadbeef" * 16  # 128 hex chars, intentionally wrong
    target = tmp_path / "evil.bin"
    session = _stub_session(payload)

    with pytest.raises(HashVerifyError, match="SHA512"):
        download_with_hash_verify(
            "https://example.invalid/x", target, sha512=bad_sha512, session=session
        )

    assert not target.exists()


def test_download_with_hash_verify_sha512_checked_before_sha1(tmp_path):
    """Both supplied: SHA-512 mismatch wins even when SHA-1 happens to match.

    Pins the helper's strong-hash-first ordering — relevant when an attacker
    has produced a SHA-1 collision on a payload that does not match the
    SHA-512 the upstream API publishes.
    """
    payload = b"hello world"
    correct_sha1 = hashlib.sha1(payload).hexdigest()
    bad_sha512 = "deadbeef" * 16
    target = tmp_path / "evil.bin"
    session = _stub_session(payload)

    with pytest.raises(HashVerifyError, match="SHA512"):
        download_with_hash_verify(
            "https://example.invalid/x",
            target,
            sha1=correct_sha1,
            sha512=bad_sha512,
            session=session,
        )

    assert not target.exists()


def test_download_with_hash_verify_network_failure_cleanup(tmp_path):
    """RequestException mid-stream: partial file is unlinked + exception re-raised."""
    target = tmp_path / "partial.bin"
    # Pre-create a stub partial file to verify cleanup actively unlinks.
    target.write_bytes(b"junk")

    session = MagicMock()
    session.get.side_effect = requests.ConnectionError("boom")

    with pytest.raises(requests.RequestException):
        download_with_hash_verify(
            "https://example.invalid/x", target, sha1="0" * 40, session=session
        )

    assert not target.exists()


def test_download_with_hash_verify_lazy_init_skips_unrequested_hashers(tmp_path):
    """When sha512 isn't requested, the SHA-512 hasher must not be constructed.

    Pins the [SMELL] fix flagged in the modrinth_client inventory: the original
    ``_download_and_verify`` always built both hashers regardless of need.
    """
    import backend.server.installer.base as base_mod

    payload = b"abc" * 100
    expected_sha1 = hashlib.sha1(payload).hexdigest()
    target = tmp_path / "lazy.bin"
    session = _stub_session(payload)

    sha512_constructed = []
    real_sha512 = hashlib.sha512

    def _spy_sha512(*args, **kwargs):
        sha512_constructed.append(True)
        return real_sha512(*args, **kwargs)

    real_hashlib = base_mod.hashlib

    class _SpyHashlib:
        sha1 = real_hashlib.sha1
        sha512 = staticmethod(_spy_sha512)

    base_mod.hashlib = _SpyHashlib  # type: ignore[assignment]
    try:
        download_with_hash_verify(
            "https://example.invalid/x", target, sha1=expected_sha1, session=session
        )
    finally:
        base_mod.hashlib = real_hashlib

    assert sha512_constructed == []


def test_download_with_hash_verify_progress_callback_sequence(tmp_path):
    """progress_callback receives (bytes_done, bytes_total) per chunk, monotonic."""
    chunks = [b"A" * 1000, b"B" * 500, b"C" * 250]
    payload = b"".join(chunks)
    expected = hashlib.sha1(payload).hexdigest()
    target = tmp_path / "stream.bin"

    session = MagicMock()
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.headers = {"Content-Length": str(len(payload))}
    response.iter_content = lambda chunk_size: iter(chunks)
    response.__enter__ = lambda self: self
    response.__exit__ = lambda *a: False
    session.get = MagicMock(return_value=response)

    events: list[tuple[int, int]] = []
    download_with_hash_verify(
        "https://example.invalid/x",
        target,
        sha1=expected,
        session=session,
        progress_callback=lambda done, total: events.append((done, total)),
    )

    bytes_done = [done for done, _ in events]
    bytes_total = [total for _, total in events]
    assert bytes_done == sorted(bytes_done)
    assert bytes_done[-1] == len(payload)
    assert all(t == len(payload) for t in bytes_total)


def test_download_with_hash_verify_swallows_progress_callback_errors(tmp_path):
    """A misbehaving progress callback must not abort the download (parity with _report)."""
    payload = b"OK"
    expected = hashlib.sha1(payload).hexdigest()
    target = tmp_path / "robust.bin"
    session = _stub_session(payload)

    def explosive(done, total):
        raise RuntimeError("never propagated")

    download_with_hash_verify(
        "https://example.invalid/x",
        target,
        sha1=expected,
        session=session,
        progress_callback=explosive,
    )

    assert target.read_bytes() == payload


# ---------- B11 Loader hard-fail invariants ----------


def test_neoforge_install_hard_fails_when_sha1_unavailable(tmp_path):
    """NeoForge: missing _fetch_expected_sha1 → install aborts with integrity message.

    Pins the S7 fix: previously a None SHA1 silently degraded to an
    unverified install (just printed a WARNING).
    """
    from backend.server.installer.neoforge import NeoForgeInstaller
    inst = NeoForgeInstaller(tmp_path)

    fake_maven = {"isSnapshot": False, "versions": ["21.1.228"]}

    session = MagicMock()

    def get(url, **_):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        if "api/maven/versions/releases" in url:
            resp.json.return_value = fake_maven
        elif url.endswith(".sha1"):
            # Empty body → _fetch_expected_sha1 returns None → hard-fail.
            resp.text = ""
        return resp

    session.get.side_effect = get
    inst.session = session

    result = inst.install("1.21.1")

    assert result.success is False
    assert "sha1" in result.message.lower() or "integrity" in result.message.lower()
    # Refusal must be BEFORE the JAR download — no installer JAR on disk.
    assert not list(tmp_path.glob("neoforge-*-installer.jar"))


def test_vanilla_install_hard_fails_when_manifest_omits_sha1(tmp_path):
    """Vanilla: missing downloads.server.sha1 in piston-meta → install refuses.

    Pins the S7 fix for vanilla: the previous code silently downloaded
    without verification when the manifest omitted the SHA1 field.
    """
    from backend.server.installer.vanilla import VanillaInstaller
    inst = VanillaInstaller(tmp_path)

    manifest = {
        "versions": [
            {"id": "1.21.4", "type": "release", "url": "https://example.invalid/v.json"}
        ],
    }
    # Note: no "sha1" key in downloads.server.
    version_meta = {
        "downloads": {"server": {"url": "https://example.invalid/server.jar"}}
    }

    session = MagicMock()

    def get(url, **_):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.headers = {"Content-Length": "0"}
        if "version_manifest" in url:
            resp.json.return_value = manifest
        elif "v.json" in url:
            resp.json.return_value = version_meta
        return resp

    session.get.side_effect = get
    inst.session = session

    result = inst.install("1.21.4")

    assert result.success is False
    assert "integrity" in result.message.lower() or "sha1" in result.message.lower()
    # No server.jar on disk: refusal happens before download.
    assert not (tmp_path / "server.jar").exists()


# ---------- B12a download_with_hash_verify atomic-write invariant ----------
#
# The helper streams bytes to a sibling ``.tmp`` file and ``os.replace``s
# into ``target`` only after the hash gate passes. A crashed download / bad
# hash leaves ``target`` UNTOUCHED — the next install pass must not observe
# a partial JAR that file-existence-checks would mistake for a complete
# artefact.


def test_download_with_hash_verify_atomic_no_partial_target_on_network_error(tmp_path):
    """Network failure mid-stream must not leave a partial ``target`` JAR."""
    target = tmp_path / "installer.jar"
    session = MagicMock()
    session.get.side_effect = requests.ConnectionError("connection reset mid-stream")

    with pytest.raises(requests.RequestException):
        download_with_hash_verify(
            "https://example.invalid/x", target, sha1="0" * 40, session=session
        )

    # Neither the final target nor any sibling .tmp may remain.
    assert not target.exists()
    assert not (tmp_path / "installer.jar.tmp").exists()


def test_download_with_hash_verify_clean_slate_on_failure_removes_existing_target(tmp_path):
    """Pre-existing ``target`` must not survive a failed re-download.

    Contract: the helper guarantees a clean slate on failure — either the
    new (verified) bytes appear at ``target``, or ``target`` is absent. A
    stale-but-present ``target`` from a prior pass would defeat the
    file-existence checks at install-resume time. Note that this test
    asserts the active-removal behaviour (B12b contract clarification:
    the docstring used to say "leaves target untouched" but the code
    has always actively unlinked the pre-existing target — we treat the
    code as the source of truth and aligned the docstring + name).
    """
    target = tmp_path / "installer.jar"
    target.write_bytes(b"stale-from-prior-run")

    session = MagicMock()
    session.get.side_effect = requests.ConnectionError("boom")

    with pytest.raises(requests.RequestException):
        download_with_hash_verify(
            "https://example.invalid/x", target, sha1="0" * 40, session=session
        )

    assert not target.exists()
    assert not (tmp_path / "installer.jar.tmp").exists()


def test_download_with_hash_verify_atomic_no_partial_target_on_hash_mismatch(tmp_path):
    """SHA1 mismatch must not leave a partial ``target`` for the next pass."""
    payload = b"hello world"
    bad_sha1 = "deadbeef" * 5  # 40 hex chars, intentionally wrong
    target = tmp_path / "installer.jar"
    session = _stub_session(payload)

    with pytest.raises(HashVerifyError, match="SHA1"):
        download_with_hash_verify(
            "https://example.invalid/x", target, sha1=bad_sha1, session=session
        )

    assert not target.exists()
    assert not (tmp_path / "installer.jar.tmp").exists()


def test_download_with_hash_verify_atomic_replace_into_target_on_success(tmp_path):
    """Success path: bytes land at ``target`` and the ``.tmp`` is gone."""
    payload = b"correct payload"
    expected = hashlib.sha1(payload).hexdigest()
    target = tmp_path / "installer.jar"
    session = _stub_session(payload)

    download_with_hash_verify(
        "https://example.invalid/x", target, sha1=expected, session=session
    )

    assert target.read_bytes() == payload
    assert not (tmp_path / "installer.jar.tmp").exists()


# ---------- B12a run_subprocess_streaming ----------
#
# Replacement for ``subprocess.run(..., capture_output=True, timeout=...)``
# at the loader-installer call sites. Streams stdout/stderr line-by-line
# through ``on_line`` callbacks (typically forwarded to ``logger.info``)
# instead of buffering tens of MB in RAM, and on timeout it kills the
# child + drains pipes before raising ``SubprocessTimeout``.


def test_run_subprocess_streaming_happy_path_collects_lines_and_exits_zero():
    """Echo three lines on stdout, exit 0; on_line fires per line."""
    import sys

    lines: list[str] = []
    completed = run_subprocess_streaming(
        [sys.executable, "-c", "print('one'); print('two'); print('three')"],
        on_line=lambda line: lines.append(line),
    )

    assert completed.returncode == 0
    assert lines == ["one", "two", "three"]
    # stdout buffer also retains the joined bytes for back-compat.
    assert "one" in completed.stdout and "three" in completed.stdout


def test_run_subprocess_streaming_failure_returncode_propagates():
    """Non-zero exit returns CompletedProcess with the actual returncode."""
    import sys

    completed = run_subprocess_streaming(
        [sys.executable, "-c", "import sys; sys.stderr.write('bad\\n'); sys.exit(7)"],
    )

    assert completed.returncode == 7
    assert "bad" in completed.stderr


def test_run_subprocess_streaming_stderr_routes_to_on_stderr_line():
    """When on_stderr_line is supplied, stderr lines go there exclusively."""
    import sys

    out_lines: list[str] = []
    err_lines: list[str] = []

    completed = run_subprocess_streaming(
        [sys.executable, "-c",
         "import sys; print('hello-out'); sys.stderr.write('hello-err\\n')"],
        on_line=lambda line: out_lines.append(line),
        on_stderr_line=lambda line: err_lines.append(line),
    )

    assert completed.returncode == 0
    assert out_lines == ["hello-out"]
    assert err_lines == ["hello-err"]


def test_run_subprocess_streaming_stderr_defaults_to_on_line():
    """Without on_stderr_line, stderr also routes to the unified on_line."""
    import sys

    lines: list[str] = []
    run_subprocess_streaming(
        [sys.executable, "-c",
         "import sys; print('out'); sys.stderr.write('err\\n')"],
        on_line=lambda line: lines.append(line),
    )

    # Both streams reached the same callback (order is non-deterministic
    # under the reader-thread fanout, so we check membership).
    assert set(lines) == {"out", "err"}


def test_run_subprocess_streaming_swallows_callback_errors():
    """A misbehaving on_line callback must not crash the runner."""
    import sys

    def explosive(line: str) -> None:
        raise RuntimeError("never propagated")

    completed = run_subprocess_streaming(
        [sys.executable, "-c", "print('hi')"],
        on_line=explosive,
    )

    assert completed.returncode == 0
    assert "hi" in completed.stdout


def test_run_subprocess_streaming_timeout_kills_and_raises():
    """A child that exceeds ``timeout`` is killed and SubprocessTimeout raised."""
    import sys

    with pytest.raises(SubprocessTimeout, match="timeout"):
        run_subprocess_streaming(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            timeout=1,
            poll_interval=0.05,
        )


def test_run_subprocess_streaming_timeout_drains_lines_before_raise():
    """Lines emitted before the kill must reach ``on_line`` before the raise.

    Pins the kill+drain contract: if the runner raised without joining the
    reader threads, observers (UI / logger) would silently lose any output
    the child produced before the timeout.
    """
    import sys

    lines: list[str] = []

    with pytest.raises(SubprocessTimeout):
        run_subprocess_streaming(
            [sys.executable, "-u", "-c",
             "import sys, time; print('before-sleep'); sys.stdout.flush(); "
             "time.sleep(30)"],
            timeout=2,
            on_line=lambda line: lines.append(line),
            poll_interval=0.05,
        )

    assert "before-sleep" in lines


def test_run_subprocess_streaming_unknown_executable_raises_oserror(tmp_path):
    """Spawn failure surfaces as OSError, distinct from SubprocessTimeout."""
    nonexistent = tmp_path / "definitely-not-a-real-binary"

    with pytest.raises((FileNotFoundError, OSError)):
        run_subprocess_streaming([str(nonexistent), "--help"])


# ---------- B12b request_with_retry ----------
#
# Wrapper around idempotent-GET callables that absorbs transient network /
# 5xx / 408 / 429 errors with exponential backoff. Cryptographic mismatches
# (HashVerifyError) and 4xx-other are NEVER retried — pinning that boundary
# is the whole point of these tests.


def _http_error_with_status(status: int) -> requests.HTTPError:
    """Build a requests.HTTPError carrying a response with ``status``."""
    response = MagicMock()
    response.status_code = status
    return requests.HTTPError(f"status {status}", response=response)


def test_request_with_retry_happy_path_first_attempt_succeeds():
    """No retry needed: callable returns on first call."""
    calls = []

    def ok():
        calls.append(1)
        return "result"

    assert request_with_retry(ok, retries=3, initial_backoff=0) == "result"
    assert calls == [1]


def test_request_with_retry_retries_on_connection_error_then_succeeds(monkeypatch):
    """ConnectionError on first attempt, success on second → returns the value."""
    monkeypatch.setattr("backend.server.installer.base.time.sleep", lambda _: None)
    attempts = []

    def flaky():
        attempts.append(len(attempts) + 1)
        if len(attempts) == 1:
            raise requests.ConnectionError("transient")
        return "ok"

    assert request_with_retry(flaky, retries=3, initial_backoff=0) == "ok"
    assert attempts == [1, 2]


def test_request_with_retry_retries_on_chunked_encoding_error(monkeypatch):
    """requests.exceptions.ChunkedEncodingError (mid-stream hiccup) retries."""
    monkeypatch.setattr("backend.server.installer.base.time.sleep", lambda _: None)
    attempts = []

    def flaky():
        attempts.append(len(attempts) + 1)
        if len(attempts) == 1:
            raise requests.exceptions.ChunkedEncodingError("mid-stream hiccup")
        return "ok"

    assert request_with_retry(flaky, retries=3, initial_backoff=0) == "ok"
    assert attempts == [1, 2]


def test_request_with_retry_retries_on_timeout(monkeypatch):
    """requests.Timeout is part of the retry whitelist."""
    monkeypatch.setattr("backend.server.installer.base.time.sleep", lambda _: None)
    attempts = []

    def flaky():
        attempts.append(1)
        if len(attempts) < 3:
            raise requests.Timeout("slow")
        return "done"

    assert request_with_retry(flaky, retries=3, initial_backoff=0) == "done"
    assert len(attempts) == 3


def test_request_with_retry_exhausts_retries_and_reraises_last(monkeypatch):
    """All attempts fail → the last exception propagates."""
    monkeypatch.setattr("backend.server.installer.base.time.sleep", lambda _: None)
    attempts = []

    def always_fails():
        attempts.append(1)
        raise requests.ConnectionError(f"attempt {len(attempts)}")

    with pytest.raises(requests.ConnectionError, match="attempt 4"):
        request_with_retry(always_fails, retries=3, initial_backoff=0)
    # 1 initial + 3 retries = 4 attempts total.
    assert len(attempts) == 4


@pytest.mark.parametrize("status", [400, 401, 403, 404])
def test_request_with_retry_does_not_retry_4xx_other(status, monkeypatch):
    """Caller-side errors (400/401/403/404) raise immediately — not transient."""
    sleeps = []
    monkeypatch.setattr(
        "backend.server.installer.base.time.sleep",
        lambda s: sleeps.append(s),
    )
    attempts = []

    def fails_4xx():
        attempts.append(1)
        raise _http_error_with_status(status)

    with pytest.raises(requests.HTTPError):
        request_with_retry(fails_4xx, retries=3, initial_backoff=0)
    assert len(attempts) == 1, "4xx-other must not retry"
    assert sleeps == [], "4xx-other must not sleep"


@pytest.mark.parametrize("status", [500, 502, 503, 504, 408, 429])
def test_request_with_retry_retries_5xx_408_429(status, monkeypatch):
    """5xx + 408 (timeout) + 429 (rate-limit) all retry until exhaustion."""
    monkeypatch.setattr("backend.server.installer.base.time.sleep", lambda _: None)
    attempts = []

    def flaky():
        attempts.append(1)
        if len(attempts) == 1:
            raise _http_error_with_status(status)
        return "recovered"

    assert request_with_retry(flaky, retries=3, initial_backoff=0) == "recovered"
    assert len(attempts) == 2


def test_request_with_retry_does_not_retry_hashverifyerror(monkeypatch):
    """A cryptographic mismatch is by definition non-transient — no retry."""
    sleeps = []
    monkeypatch.setattr(
        "backend.server.installer.base.time.sleep",
        lambda s: sleeps.append(s),
    )
    attempts = []

    def hash_fail():
        attempts.append(1)
        raise HashVerifyError("SHA1 mismatch")

    with pytest.raises(HashVerifyError):
        request_with_retry(hash_fail, retries=3, initial_backoff=0)
    assert len(attempts) == 1
    assert sleeps == []


def test_request_with_retry_does_not_retry_value_error(monkeypatch):
    """Non-whitelisted exceptions surface immediately (no implicit catch-all)."""
    sleeps = []
    monkeypatch.setattr(
        "backend.server.installer.base.time.sleep",
        lambda s: sleeps.append(s),
    )
    attempts = []

    def boom():
        attempts.append(1)
        raise ValueError("caller bug")

    with pytest.raises(ValueError, match="caller bug"):
        request_with_retry(boom, retries=3, initial_backoff=0)
    assert len(attempts) == 1
    assert sleeps == []


def test_request_with_retry_on_retry_callback_invoked_with_attempt_and_exc(monkeypatch):
    """on_retry receives (1-indexed attempt, exception) for each retry."""
    monkeypatch.setattr("backend.server.installer.base.time.sleep", lambda _: None)
    seen: list[tuple[int, BaseException]] = []
    attempts = []

    def flaky():
        attempts.append(1)
        if len(attempts) < 3:
            raise requests.ConnectionError(f"hiccup {len(attempts)}")
        return "ok"

    request_with_retry(
        flaky,
        retries=3,
        initial_backoff=0,
        on_retry=lambda n, exc: seen.append((n, exc)),
    )
    # Two retries scheduled (after attempt 1 and attempt 2).
    assert [n for n, _ in seen] == [1, 2]
    assert all(isinstance(exc, requests.ConnectionError) for _, exc in seen)


def test_request_with_retry_swallows_on_retry_errors(monkeypatch):
    """A misbehaving on_retry callback must not abort the retry loop."""
    monkeypatch.setattr("backend.server.installer.base.time.sleep", lambda _: None)
    attempts = []

    def flaky():
        attempts.append(1)
        if len(attempts) < 2:
            raise requests.ConnectionError("once")
        return "ok"

    def explosive(_n, _exc):
        raise RuntimeError("never propagated")

    assert request_with_retry(
        flaky, retries=3, initial_backoff=0, on_retry=explosive
    ) == "ok"
    assert len(attempts) == 2


def test_request_with_retry_zero_retries_is_single_attempt(monkeypatch):
    """retries=0 → no retry on transient errors; raise immediately."""
    sleeps = []
    monkeypatch.setattr(
        "backend.server.installer.base.time.sleep",
        lambda s: sleeps.append(s),
    )
    attempts = []

    def flaky():
        attempts.append(1)
        raise requests.ConnectionError("once")

    with pytest.raises(requests.ConnectionError):
        request_with_retry(flaky, retries=0, initial_backoff=0)
    assert len(attempts) == 1
    assert sleeps == []


# ---------- B12b download_with_hash_verify retries opt-in ----------


def test_download_with_hash_verify_retries_param_retries_transient_failure(
    tmp_path, monkeypatch
):
    """retries=3 absorbs a transient ConnectionError on the first call."""
    monkeypatch.setattr("backend.server.installer.base.time.sleep", lambda _: None)
    payload = b"hello world"
    expected_sha1 = hashlib.sha1(payload).hexdigest()
    target = tmp_path / "out.bin"

    call_count = []

    def make_response():
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.headers = {"Content-Length": str(len(payload))}
        resp.iter_content = lambda chunk_size: iter([payload])
        resp.__enter__ = lambda self: self
        resp.__exit__ = lambda *a: False
        return resp

    def flaky_get(url, **kwargs):
        call_count.append(1)
        if len(call_count) == 1:
            raise requests.ConnectionError("transient")
        return make_response()

    session = MagicMock()
    session.get = flaky_get

    download_with_hash_verify(
        "https://example.invalid/x",
        target,
        sha1=expected_sha1,
        session=session,
        retries=3,
    )

    assert target.read_bytes() == payload
    assert len(call_count) == 2  # one failure + one retry success


def test_download_with_hash_verify_retries_does_not_retry_hash_mismatch(
    tmp_path, monkeypatch
):
    """retries=3 must NOT mask a SHA1 mismatch — cryptographic, never transient."""
    monkeypatch.setattr("backend.server.installer.base.time.sleep", lambda _: None)
    payload = b"hello world"
    bad_sha1 = "deadbeef" * 5
    target = tmp_path / "evil.bin"
    session = _stub_session(payload)

    with pytest.raises(HashVerifyError, match="SHA1"):
        download_with_hash_verify(
            "https://example.invalid/x",
            target,
            sha1=bad_sha1,
            session=session,
            retries=3,
        )

    # _stub_session.get is a MagicMock; we can read its call_count.
    assert session.get.call_count == 1, "HashVerifyError must not trigger retry"
    assert not target.exists()


def test_download_with_hash_verify_retries_zero_default_keeps_legacy_contract(
    tmp_path,
):
    """Default retries=0 → first transient error propagates (legacy behaviour)."""
    target = tmp_path / "out.bin"
    session = MagicMock()
    session.get.side_effect = requests.ConnectionError("boom")

    with pytest.raises(requests.RequestException):
        download_with_hash_verify(
            "https://example.invalid/x", target, sha1="0" * 40, session=session
        )
    assert session.get.call_count == 1


# ---------- B12b Forge _fetch_expected_sha1 empty-body robustness ----------
#
# The previous implementation collapsed empty / whitespace-only / non-hex
# responses through an IndexError-swallow; the call site then silently
# degraded to "no integrity check". B12b: every shape that isn't a real
# 40-char hex SHA-1 returns None deterministically, and the retry helper
# absorbs transient 5xx that previously fell through the same path.


def _stub_forge_session_with_sha1_text(sha1_text: str) -> MagicMock:
    """Stub a session whose .sha1 endpoint returns ``sha1_text``."""
    session = MagicMock()

    def get(url, **_):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        if url.endswith(".sha1"):
            resp.text = sha1_text
        return resp

    session.get.side_effect = get
    return session


def test_forge_fetch_expected_sha1_returns_token_for_valid_response(tmp_path):
    """Happy path: 40-char hex token is returned lowercased."""
    from backend.server.installer.forge import ForgeInstaller
    inst = ForgeInstaller(tmp_path)
    inst.session = _stub_forge_session_with_sha1_text("ABC" + "1" * 37)

    out = inst._fetch_expected_sha1("1.20.1", "47.4.10")
    assert out == ("abc" + "1" * 37)


def test_forge_fetch_expected_sha1_returns_none_for_empty_body(tmp_path):
    """Empty body → None (was IndexError-swallowed before B12b)."""
    from backend.server.installer.forge import ForgeInstaller
    inst = ForgeInstaller(tmp_path)
    inst.session = _stub_forge_session_with_sha1_text("")

    assert inst._fetch_expected_sha1("1.20.1", "47.4.10") is None


def test_forge_fetch_expected_sha1_returns_none_for_whitespace_only_body(tmp_path):
    """Whitespace-only body → None."""
    from backend.server.installer.forge import ForgeInstaller
    inst = ForgeInstaller(tmp_path)
    inst.session = _stub_forge_session_with_sha1_text("   \n\t  ")

    assert inst._fetch_expected_sha1("1.20.1", "47.4.10") is None


def test_forge_fetch_expected_sha1_returns_none_for_short_token(tmp_path):
    """Short / wrong-length token → None."""
    from backend.server.installer.forge import ForgeInstaller
    inst = ForgeInstaller(tmp_path)
    inst.session = _stub_forge_session_with_sha1_text("abc123")

    assert inst._fetch_expected_sha1("1.20.1", "47.4.10") is None


def test_forge_fetch_expected_sha1_returns_none_for_non_hex_token(tmp_path):
    """40-char but contains non-hex chars → None."""
    from backend.server.installer.forge import ForgeInstaller
    inst = ForgeInstaller(tmp_path)
    # 40 chars but with 'z' (non-hex).
    inst.session = _stub_forge_session_with_sha1_text("z" + "0" * 39)

    assert inst._fetch_expected_sha1("1.20.1", "47.4.10") is None


def test_forge_fetch_expected_sha1_strips_filename_suffix(tmp_path):
    """Some Maven sha1 endpoints emit '<hash>  <filename>' — first token wins."""
    from backend.server.installer.forge import ForgeInstaller
    inst = ForgeInstaller(tmp_path)
    sha1 = "a" * 40
    inst.session = _stub_forge_session_with_sha1_text(
        f"{sha1}  forge-1.20.1-47.4.10-installer.jar\n"
    )

    assert inst._fetch_expected_sha1("1.20.1", "47.4.10") == sha1


# ---------- B12b NeoForge _fetch_expected_sha1 empty-body robustness ----------


def _stub_neoforge_session_with_sha1_text(sha1_text: str) -> MagicMock:
    """Stub a session whose .sha1 endpoint returns ``sha1_text``."""
    session = MagicMock()

    def get(url, **_):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        if url.endswith(".sha1"):
            resp.text = sha1_text
        return resp

    session.get.side_effect = get
    return session


def test_neoforge_fetch_expected_sha1_returns_none_for_empty_body(tmp_path):
    """Empty body parity with the Forge fix."""
    from backend.server.installer.neoforge import NeoForgeInstaller
    inst = NeoForgeInstaller(tmp_path)
    inst.session = _stub_neoforge_session_with_sha1_text("")

    assert inst._fetch_expected_sha1("21.1.228") is None


def test_neoforge_fetch_expected_sha1_returns_none_for_non_hex(tmp_path):
    """Non-hex token parity with the Forge fix."""
    from backend.server.installer.neoforge import NeoForgeInstaller
    inst = NeoForgeInstaller(tmp_path)
    inst.session = _stub_neoforge_session_with_sha1_text("g" * 40)

    assert inst._fetch_expected_sha1("21.1.228") is None
