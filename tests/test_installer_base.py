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
    _validate_version_token,
    download_with_hash_verify,
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
# ``_validate_version_token`` before it lands in a filename or subprocess
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
    assert _validate_version_token(good, field_name="mc_version") == good


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
])
def test_validate_version_token_rejects_path_and_shell_metachars(bad):
    with pytest.raises(ValueError, match="Invalid mc_version"):
        _validate_version_token(bad, field_name="mc_version")


def test_validate_version_token_rejects_non_string():
    with pytest.raises(ValueError, match="Invalid build"):
        _validate_version_token(None, field_name="build")  # type: ignore[arg-type]


def test_validate_version_token_field_name_in_error_message():
    """Error must name the field so install routes can log a clear failure."""
    with pytest.raises(ValueError, match="loader_version"):
        _validate_version_token("..", field_name="loader_version")


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
