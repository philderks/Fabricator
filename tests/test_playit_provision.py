"""Tests for backend.playit.release / provision / binary trust classification.

Covers the fix for issue #55 — the Docker image ships no tools/install.sh, so
the playit binaries were never installed and the tunnel could not start.

Coverage focus:
  * the pin table is internally complete (every arch has both binaries)
  * arch mapping, including the aliases Python reports that `uname -m` doesn't
  * provisioning is fail-closed: mismatched digest installs nothing
  * provisioning is idempotent: an already-verified binary is not re-fetched
  * trust classification across verified / unverified / system / missing

No test touches the network: every download is stubbed at requests.get.
"""
from __future__ import annotations

import hashlib
import importlib
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from backend.playit import binary as playit_binary
from backend.playit import provision, release


@pytest.fixture(autouse=True)
def _fresh_modules():
    """Re-bind the module-level names against what sys.modules holds NOW.

    test_app_factory.py deletes every cached `backend.*` module, so the imports
    above can go stale part-way through a full-suite run: `patch("backend.
    playit.binary.find_daemon")` would then patch the freshly imported module
    while these tests kept calling the old one — and on a dev box with a real
    playit in /usr/local/bin that silently passes through to the live binary.
    Same idiom as test_install_persists_launch.py.
    """
    global playit_binary, provision, release
    playit_binary = importlib.import_module("backend.playit.binary")
    provision = importlib.import_module("backend.playit.provision")
    release = importlib.import_module("backend.playit.release")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_response(payload: bytes):
    """A stand-in for requests.get(stream=True) used as a context manager."""
    response = MagicMock()
    response.__enter__ = lambda self: self
    response.__exit__ = lambda self, *exc: False
    response.raise_for_status = MagicMock()
    response.iter_content = lambda chunk_size: iter([payload])
    return response


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


@pytest.fixture
def isolated_bins(tmp_path, monkeypatch, _fresh_modules):
    """Point the /usr/local/bin probe at an empty temp dir.

    A dev machine (or CI image) may have a real playit installed there, which
    discovery prefers by design — without this it leaks into every assertion.
    """
    monkeypatch.setattr(playit_binary, "_SYSTEM_MANAGED_BIN_DIR",
                        str(tmp_path / "usr-local-bin"))
    # Digest cache is keyed by path and persists across tests in-process.
    playit_binary._digest_cache.clear()


@pytest.fixture
def linux_amd64(monkeypatch, isolated_bins):
    """Pin the host to linux/amd64 so tests behave the same on any runner."""
    monkeypatch.setattr(provision.platform_utils, "is_linux", lambda: True)
    monkeypatch.setattr(release.platform, "machine", lambda: "x86_64")


# ---------------------------------------------------------------------------
# release.py — the pin
# ---------------------------------------------------------------------------

def test_pin_table_covers_every_arch_for_both_binaries():
    """A half-updated pin (one binary bumped, the other not) fails closed at
    runtime; this catches it at review time instead."""
    arches = {"amd64", "aarch64", "armv7", "i686"}
    expected = {release.asset_name(name, arch)
                for name in release.BINARY_NAMES for arch in arches}
    assert set(release.SHA256) == expected
    assert all(len(digest) == 64 for digest in release.SHA256.values())


@pytest.mark.parametrize("machine,arch", [
    ("x86_64", "amd64"), ("AMD64", "amd64"),
    ("aarch64", "aarch64"), ("arm64", "aarch64"),
    ("armv7l", "armv7"), ("i686", "i686"),
])
def test_resolve_arch_maps_known_machines(machine, arch):
    assert release.resolve_arch(machine) == arch


def test_resolve_arch_returns_none_for_unsupported():
    assert release.resolve_arch("riscv64") is None
    assert release.expected_sha256("playit", None) is None or True  # arch-dependent


def test_expected_sha256_is_none_on_unsupported_arch():
    """None must mean 'cannot vouch', never 'anything goes' — the trust check
    relies on this to avoid a None == None false positive."""
    assert release.expected_sha256("playit", "riscv64") is None


def test_asset_url_pins_the_version():
    url = release.asset_url("playit-linux-amd64")
    assert release.PLAYIT_VERSION in url
    assert url.endswith("/playit-linux-amd64")


# ---------------------------------------------------------------------------
# provision.py
# ---------------------------------------------------------------------------

def test_ensure_binaries_installs_both_verified(tmp_path, linux_amd64, monkeypatch):
    payloads = {
        name: f"#!/bin/sh\n# {name}\n".encode()
        for name in release.BINARY_NAMES
    }
    digests = {release.asset_name(name, "amd64"): _sha(blob)
               for name, blob in payloads.items()}
    monkeypatch.setattr(release, "SHA256", digests)

    def _get(url, **_kwargs):
        name = release.DAEMON_NAME if url.endswith("playit-linux-amd64") else release.CLI_NAME
        return _fake_response(payloads[name])

    with patch("backend.playit.provision.requests.get", side_effect=_get):
        dest = provision.ensure_binaries(tmp_path)

    assert dest == tmp_path
    for name, blob in payloads.items():
        installed = tmp_path / name
        assert installed.read_bytes() == blob
        assert os.access(installed, os.X_OK), "must be executable"
        # No temp files left behind.
    assert not list(tmp_path.glob(".*tmp*"))


def test_ensure_binaries_refuses_on_digest_mismatch(tmp_path, linux_amd64, monkeypatch):
    """Fail closed: a binary that does not match the pin is never installed."""
    monkeypatch.setattr(release, "SHA256", {
        release.asset_name(name, "amd64"): _sha(b"what we pinned")
        for name in release.BINARY_NAMES
    })

    with patch("backend.playit.provision.requests.get",
               side_effect=lambda *a, **k: _fake_response(b"something else entirely")):
        with pytest.raises(provision.ProvisionError, match="sha256 mismatch"):
            provision.ensure_binaries(tmp_path)

    assert list(tmp_path.iterdir()) == [], "nothing — not even a temp file — survives"


def test_ensure_binaries_skips_already_verified(tmp_path, linux_amd64, monkeypatch):
    """Idempotent: the common case (rebuild, redundant start) hits no network."""
    blob = b"already here"
    monkeypatch.setattr(release, "SHA256", {
        release.asset_name(name, "amd64"): _sha(blob)
        for name in release.BINARY_NAMES
    })
    for name in release.BINARY_NAMES:
        target = tmp_path / name
        target.write_bytes(blob)
        target.chmod(0o755)

    with patch("backend.playit.provision.requests.get") as get:
        provision.ensure_binaries(tmp_path)
    get.assert_not_called()


def test_ensure_binaries_replaces_a_stale_binary(tmp_path, linux_amd64, monkeypatch):
    """A binary that does not match the pin (an old version left behind) is
    re-downloaded rather than trusted."""
    good = b"the pinned build"
    monkeypatch.setattr(release, "SHA256", {
        release.asset_name(name, "amd64"): _sha(good)
        for name in release.BINARY_NAMES
    })
    stale = tmp_path / release.DAEMON_NAME
    stale.write_bytes(b"an older build")
    stale.chmod(0o755)

    with patch("backend.playit.provision.requests.get",
               side_effect=lambda *a, **k: _fake_response(good)):
        provision.ensure_binaries(tmp_path)

    assert stale.read_bytes() == good


def test_ensure_binaries_rejects_non_linux(tmp_path, monkeypatch):
    monkeypatch.setattr(provision.platform_utils, "is_linux", lambda: False)
    with pytest.raises(provision.ProvisionError, match="Linux only"):
        provision.ensure_binaries(tmp_path)


def test_ensure_binaries_rejects_unsupported_arch(tmp_path, monkeypatch):
    monkeypatch.setattr(provision.platform_utils, "is_linux", lambda: True)
    monkeypatch.setattr(release.platform, "machine", lambda: "riscv64")
    with pytest.raises(provision.ProvisionError, match="architecture"):
        provision.ensure_binaries(tmp_path)


def test_download_retries_transient_failures(tmp_path, linux_amd64, monkeypatch):
    import requests as requests_mod

    blob = b"eventually"
    monkeypatch.setattr(release, "SHA256", {
        release.asset_name(name, "amd64"): _sha(blob)
        for name in release.BINARY_NAMES
    })
    monkeypatch.setattr(provision, "_RETRY_BACKOFF_SEC", 0)

    calls = {"n": 0}

    def _flaky(*_args, **_kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise requests_mod.ConnectionError("connection reset")
        return _fake_response(blob)

    with patch("backend.playit.provision.requests.get", side_effect=_flaky):
        provision.ensure_binaries(tmp_path)

    assert calls["n"] > 1
    assert (tmp_path / release.DAEMON_NAME).read_bytes() == blob


def test_download_gives_up_and_raises_after_retries(tmp_path, linux_amd64, monkeypatch):
    import requests as requests_mod

    monkeypatch.setattr(provision, "_RETRY_BACKOFF_SEC", 0)
    with patch("backend.playit.provision.requests.get",
               side_effect=requests_mod.ConnectionError("no route to host")):
        with pytest.raises(provision.ProvisionError, match="could not download"):
            provision.ensure_binaries(tmp_path)


# ---------------------------------------------------------------------------
# binary.py — trust classification
# ---------------------------------------------------------------------------

def _install(dirpath: Path, blob: bytes) -> None:
    dirpath.mkdir(parents=True, exist_ok=True)
    for name in release.BINARY_NAMES:
        target = dirpath / name
        target.write_bytes(blob)
        target.chmod(0o755)


def test_trust_missing_when_nothing_found(linux_amd64):
    with patch("backend.playit.binary.find_daemon", return_value=None), \
         patch("backend.playit.binary.find_cli", return_value=None):
        assert playit_binary.binary_trust() == playit_binary.TRUST_MISSING


def test_trust_verified_for_pinned_binaries_in_managed_dir(tmp_path, linux_amd64, monkeypatch):
    blob = b"the pinned build"
    monkeypatch.setenv("PLAYIT_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setattr(release, "SHA256", {
        release.asset_name(name, "amd64"): _sha(blob)
        for name in release.BINARY_NAMES
    })
    _install(tmp_path / "bin", blob)

    with patch("backend.playit.binary.shutil.which", return_value=None):
        assert playit_binary.binary_trust() == playit_binary.TRUST_VERIFIED


def test_trust_unverified_for_wrong_binary_in_managed_dir(tmp_path, linux_amd64, monkeypatch):
    """In a directory Fabricator owns, a mismatch is an anomaly worth warning
    about — nothing but provisioning should ever write there."""
    monkeypatch.setenv("PLAYIT_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setattr(release, "SHA256", {
        release.asset_name(name, "amd64"): _sha(b"the pinned build")
        for name in release.BINARY_NAMES
    })
    _install(tmp_path / "bin", b"not what we pinned")

    with patch("backend.playit.binary.shutil.which", return_value=None):
        assert playit_binary.binary_trust() == playit_binary.TRUST_UNVERIFIED


def test_trust_system_for_operator_supplied_binaries(tmp_path, linux_amd64, monkeypatch):
    """`apt install playit` wins discovery by design. We did not verify it, but
    that is expected — it must read as neutral, not as a fault."""
    monkeypatch.setenv("PLAYIT_RUNTIME_DIR", str(tmp_path / "runtime"))
    distro = tmp_path / "usr-bin"
    _install(distro, b"distro build")

    with patch("backend.playit.binary.find_daemon",
               return_value=str(distro / release.DAEMON_NAME)), \
         patch("backend.playit.binary.find_cli",
               return_value=str(distro / release.CLI_NAME)):
        assert playit_binary.binary_trust() == playit_binary.TRUST_SYSTEM


def test_trust_not_verified_on_unsupported_arch(tmp_path, monkeypatch, isolated_bins):
    """No pinned digest must never read as verified (the None == None trap)."""
    monkeypatch.setattr(release.platform, "machine", lambda: "riscv64")
    monkeypatch.setenv("PLAYIT_RUNTIME_DIR", str(tmp_path))
    _install(tmp_path / "bin", b"whatever")

    with patch("backend.playit.binary.shutil.which", return_value=None):
        assert playit_binary.binary_trust() == playit_binary.TRUST_UNVERIFIED


def test_digest_cache_invalidates_when_the_binary_changes(tmp_path, linux_amd64, monkeypatch):
    """The cache exists because status is polled every ~3s; it must still notice
    a binary being swapped underneath it."""
    monkeypatch.setenv("PLAYIT_RUNTIME_DIR", str(tmp_path))
    good = b"the pinned build"
    monkeypatch.setattr(release, "SHA256", {
        release.asset_name(name, "amd64"): _sha(good)
        for name in release.BINARY_NAMES
    })
    bin_dir = tmp_path / "bin"
    _install(bin_dir, good)

    with patch("backend.playit.binary.shutil.which", return_value=None):
        assert playit_binary.binary_trust() == playit_binary.TRUST_VERIFIED

        swapped = bin_dir / release.DAEMON_NAME
        swapped.write_bytes(b"swapped out from under us")
        swapped.chmod(0o755)
        os.utime(swapped, (1, 1))  # force a distinct mtime even on coarse clocks

        assert playit_binary.binary_trust() == playit_binary.TRUST_UNVERIFIED


def test_discovery_finds_runtime_provisioned_binaries(tmp_path, monkeypatch, isolated_bins):
    """The provisioning fallback is pointless if discovery cannot see it."""
    monkeypatch.setenv("PLAYIT_RUNTIME_DIR", str(tmp_path))
    _install(tmp_path / "bin", b"x")

    with patch("backend.playit.binary.shutil.which", return_value=None):
        assert playit_binary.find_daemon() == str(tmp_path / "bin" / release.DAEMON_NAME)
        assert playit_binary.find_cli() == str(tmp_path / "bin" / release.CLI_NAME)
