"""Per-loader progress-callback emission tests.

Each loader emits a documented phase sequence in order. Bytes-progress
emissions for download phases must have monotonically non-decreasing
bytes_done and a stable bytes_total. Failure paths must emit ``failed``
with a non-empty error.
"""
from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def _record(events: list):
    """Build a callback that appends (phase, detail) tuples to events."""
    def cb(phase, detail):
        events.append((phase, dict(detail)))
    return cb


def _phases(events) -> list[str]:
    return [phase for phase, _ in events]


# ----- Fabric -----

def test_fabric_install_emits_phases_in_order(tmp_path, monkeypatch):
    from backend.server.installer.fabric import FabricInstaller
    inst = FabricInstaller(tmp_path)

    monkeypatch.setattr(inst, "_get_latest_loader_version", lambda mc: "0.16.0")
    monkeypatch.setattr(inst, "_get_latest_installer_version", lambda: "1.0.0")
    fake_jar = tmp_path / "server.jar"
    fake_jar.write_bytes(b"PK\x03\x04")
    monkeypatch.setattr(
        inst, "_download_server_jar", lambda mc, lv, iv, **kw: fake_jar
    )

    events = []
    result = inst.install("1.21.4", progress_callback=_record(events))
    assert result.success is True

    phases = _phases(events)
    # Ordering — starting first, done last, no terminal phases mid-run.
    assert phases[0] == "starting"
    assert phases[-1] == "done"
    assert "resolving_versions" in phases
    assert "writing_eula" in phases
    # No 'failed' anywhere on success path.
    assert "failed" not in phases


def test_fabric_install_failure_emits_failed_with_error(tmp_path, monkeypatch):
    from backend.server.installer.fabric import FabricInstaller
    inst = FabricInstaller(tmp_path)

    # Force resolution failure.
    monkeypatch.setattr(inst, "_get_latest_loader_version", lambda mc: None)

    events = []
    result = inst.install("1.21.4", progress_callback=_record(events))
    assert result.success is False
    assert ("failed", events[-1][1]) == events[-1]
    assert events[-1][0] == "failed"
    assert events[-1][1].get("error")  # non-empty


def test_fabric_download_emits_bytes_progress(tmp_path, monkeypatch):
    """downloading_server_jar emissions: bytes_done monotonic, bytes_total stable."""
    from backend.server.installer.fabric import FabricInstaller
    inst = FabricInstaller(tmp_path)

    # Replace the network session.get for the JAR download. Stream three
    # chunks; the installer should emit a bytes_done update per chunk.
    chunks = [b"A" * 1000, b"B" * 1500, b"C" * 500]
    total = sum(len(c) for c in chunks)

    session_resp = MagicMock()
    session_resp.raise_for_status = MagicMock()
    session_resp.headers = {"Content-Length": str(total), "Content-Type": "application/java-archive"}
    session_resp.iter_content = lambda chunk_size: iter(chunks)
    session_resp.__enter__ = lambda s: s
    session_resp.__exit__ = lambda *a: False

    inst.session = MagicMock()
    inst.session.get = MagicMock(return_value=session_resp)

    monkeypatch.setattr(inst, "_get_latest_loader_version", lambda mc: "0.16.0")
    monkeypatch.setattr(inst, "_get_latest_installer_version", lambda: "1.0.0")

    events = []
    result = inst.install("1.21.4", progress_callback=_record(events))
    assert result.success is True

    download_events = [e for e in events if e[0] == "downloading_server_jar"]
    assert len(download_events) >= 3  # at least one per chunk

    bytes_done_seq = [e[1]["bytes_done"] for e in download_events]
    bytes_total_seq = [e[1]["bytes_total"] for e in download_events]
    # Monotonic non-decreasing.
    assert bytes_done_seq == sorted(bytes_done_seq)
    # Stable total.
    assert all(t == total for t in bytes_total_seq)
    # Final value matches total.
    assert bytes_done_seq[-1] == total


# ----- Vanilla -----

def test_vanilla_install_emits_phases_in_order(tmp_path):
    from backend.server.installer.vanilla import VanillaInstaller
    inst = VanillaInstaller(tmp_path)

    jar_bytes = b"VANILLA"
    sha1 = hashlib.sha1(jar_bytes).hexdigest()

    fake_manifest = {
        "versions": [{"id": "1.21.4", "type": "release", "url": "https://example.invalid/1.21.4.json"}]
    }
    fake_version_meta = {
        "downloads": {"server": {"url": "https://example.invalid/server.jar", "sha1": sha1, "size": len(jar_bytes)}}
    }

    session = MagicMock()
    def get(url, **_):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.headers = {"Content-Length": str(len(jar_bytes))}
        if "version_manifest" in url:
            resp.json.return_value = fake_manifest
        elif "1.21.4.json" in url:
            resp.json.return_value = fake_version_meta
        elif "server.jar" in url:
            resp.iter_content = lambda chunk_size: iter([jar_bytes])
            resp.__enter__ = lambda s: s
            resp.__exit__ = lambda *a: False
        return resp
    session.get.side_effect = get
    inst.session = session

    events = []
    result = inst.install("1.21.4", progress_callback=_record(events))
    assert result.success is True

    phases = _phases(events)
    assert phases[0] == "starting"
    assert phases[-1] == "done"
    assert "resolving_versions" in phases
    assert "downloading_server_jar" in phases
    assert "writing_eula" in phases
    assert "failed" not in phases


def test_vanilla_install_failure_emits_failed(tmp_path):
    from backend.server.installer.vanilla import VanillaInstaller
    inst = VanillaInstaller(tmp_path)
    import requests
    session = MagicMock()
    session.get.side_effect = requests.RequestException("boom")
    inst.session = session

    events = []
    result = inst.install("1.21.4", progress_callback=_record(events))
    assert result.success is False
    assert events[-1][0] == "failed"
    assert events[-1][1].get("error")


def test_vanilla_download_bytes_monotonic(tmp_path):
    from backend.server.installer.vanilla import VanillaInstaller
    inst = VanillaInstaller(tmp_path)

    chunks = [b"X" * 700, b"Y" * 800, b"Z" * 1500]
    total = sum(len(c) for c in chunks)
    sha1 = hashlib.sha1(b"".join(chunks)).hexdigest()

    fake_manifest = {
        "versions": [{"id": "1.21.4", "type": "release", "url": "https://example.invalid/v.json"}]
    }
    fake_version_meta = {
        "downloads": {"server": {"url": "https://example.invalid/server.jar", "sha1": sha1, "size": total}}
    }

    session = MagicMock()
    def get(url, **_):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.headers = {"Content-Length": str(total)}
        if "version_manifest" in url:
            resp.json.return_value = fake_manifest
        elif "v.json" in url:
            resp.json.return_value = fake_version_meta
        elif "server.jar" in url:
            resp.iter_content = lambda chunk_size: iter(chunks)
            resp.__enter__ = lambda s: s
            resp.__exit__ = lambda *a: False
        return resp
    session.get.side_effect = get
    inst.session = session

    events = []
    result = inst.install("1.21.4", progress_callback=_record(events))
    assert result.success is True

    dl = [e for e in events if e[0] == "downloading_server_jar"]
    assert len(dl) >= 3
    bytes_done = [e[1]["bytes_done"] for e in dl]
    assert bytes_done == sorted(bytes_done)
    assert bytes_done[-1] == total


# ----- Quilt -----

def test_quilt_install_emits_subprocess_phases(tmp_path, monkeypatch):
    from backend.server.installer.quilt import QuiltInstaller
    inst = QuiltInstaller(tmp_path)

    bytes_payload = b"PKquilt"
    session = MagicMock()
    def get(url, **_):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.headers = {"Content-Length": str(len(bytes_payload))}
        if "/v3/versions/game" in url:
            resp.json.return_value = [{"version": "1.21.4", "stable": True}]
        elif url.endswith("maven-metadata.xml"):
            resp.text = "<metadata><versioning><release>0.12.1</release></versioning></metadata>"
        elif url.endswith(".jar"):
            resp.iter_content = lambda chunk_size: iter([bytes_payload])
            resp.__enter__ = lambda s: s
            resp.__exit__ = lambda *a: False
        elif url.endswith(".sha1"):
            resp.text = hashlib.sha1(bytes_payload).hexdigest()
        return resp
    session.get.side_effect = get
    inst.session = session

    def fake_run(cmd, **kwargs):
        (tmp_path / "quilt-server-launch.jar").write_bytes(b"PK")
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")
    monkeypatch.setattr("backend.server.installer.quilt.subprocess.run", fake_run)

    events = []
    result = inst.install("1.21.4", progress_callback=_record(events))
    assert result.success is True

    phases = _phases(events)
    expected_subset = [
        "starting", "resolving_versions", "downloading_installer",
        "verifying", "running_installer", "detecting_artifacts",
        "writing_eula", "done",
    ]
    # Each expected phase appears, and they appear in this relative order.
    last_idx = -1
    for needed in expected_subset:
        idx = phases.index(needed) if needed in phases else -1
        assert idx > last_idx, f"phase {needed!r} missing or out of order in {phases!r}"
        last_idx = idx


def test_quilt_install_failure_emits_failed(tmp_path, monkeypatch):
    from backend.server.installer.quilt import QuiltInstaller
    inst = QuiltInstaller(tmp_path)
    import requests
    session = MagicMock()
    session.get.side_effect = requests.RequestException("network down")
    inst.session = session

    events = []
    result = inst.install("1.21.4", progress_callback=_record(events))
    assert result.success is False
    assert events[-1][0] == "failed"
    assert events[-1][1].get("error")


def test_quilt_download_installer_bytes_monotonic(tmp_path, monkeypatch):
    from backend.server.installer.quilt import QuiltInstaller
    inst = QuiltInstaller(tmp_path)

    chunks = [b"A" * 800, b"B" * 700]
    total = sum(len(c) for c in chunks)
    payload = b"".join(chunks)
    sha1 = hashlib.sha1(payload).hexdigest()

    session = MagicMock()
    def get(url, **_):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.headers = {"Content-Length": str(total)}
        if "/v3/versions/game" in url:
            resp.json.return_value = [{"version": "1.21.4", "stable": True}]
        elif url.endswith("maven-metadata.xml"):
            resp.text = "<metadata><versioning><release>0.12.1</release></versioning></metadata>"
        elif url.endswith(".jar"):
            resp.iter_content = lambda chunk_size: iter(chunks)
            resp.__enter__ = lambda s: s
            resp.__exit__ = lambda *a: False
        elif url.endswith(".sha1"):
            resp.text = sha1
        return resp
    session.get.side_effect = get
    inst.session = session

    def fake_run(cmd, **kwargs):
        (tmp_path / "quilt-server-launch.jar").write_bytes(b"PK")
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")
    monkeypatch.setattr("backend.server.installer.quilt.subprocess.run", fake_run)

    events = []
    result = inst.install("1.21.4", progress_callback=_record(events))
    assert result.success is True

    dl = [e for e in events if e[0] == "downloading_installer"]
    assert len(dl) >= 2
    bytes_done = [e[1]["bytes_done"] for e in dl]
    assert bytes_done == sorted(bytes_done)
    assert bytes_done[-1] == total


# ----- NeoForge -----

def test_neoforge_install_emits_phases_in_order(tmp_path, monkeypatch):
    from backend.server.installer.neoforge import NeoForgeInstaller
    inst = NeoForgeInstaller(tmp_path)

    bytes_payload = b"PKneoforge"
    session = MagicMock()
    def get(url, **_):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.headers = {"Content-Length": str(len(bytes_payload))}
        if "/api/maven/versions/releases" in url:
            resp.json.return_value = {"versions": ["21.1.228"]}
        elif url.endswith(".jar"):
            resp.iter_content = lambda chunk_size: iter([bytes_payload])
            resp.__enter__ = lambda s: s
            resp.__exit__ = lambda *a: False
        elif url.endswith(".sha1"):
            resp.text = hashlib.sha1(bytes_payload).hexdigest()
        return resp
    session.get.side_effect = get
    inst.session = session

    def fake_run(cmd, **kwargs):
        target = tmp_path / "libraries" / "net" / "neoforged" / "neoforge" / "21.1.228"
        target.mkdir(parents=True, exist_ok=True)
        (target / "unix_args.txt").write_text("# args\n")
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")
    monkeypatch.setattr("backend.server.installer.neoforge.subprocess.run", fake_run)
    monkeypatch.setattr("backend.server.installer.neoforge.is_windows", lambda: False)

    events = []
    result = inst.install("1.21.1", progress_callback=_record(events))
    assert result.success is True

    phases = _phases(events)
    expected_subset = [
        "starting", "resolving_versions", "downloading_installer",
        "verifying", "running_installer", "detecting_artifacts",
        "writing_eula", "done",
    ]
    last_idx = -1
    for needed in expected_subset:
        idx = phases.index(needed) if needed in phases else -1
        assert idx > last_idx, f"phase {needed!r} missing or out of order in {phases!r}"
        last_idx = idx


def test_neoforge_install_failure_emits_failed(tmp_path):
    from backend.server.installer.neoforge import NeoForgeInstaller
    inst = NeoForgeInstaller(tmp_path)
    import requests
    session = MagicMock()
    session.get.side_effect = requests.RequestException("boom")
    inst.session = session

    events = []
    result = inst.install("1.21.1", progress_callback=_record(events))
    assert result.success is False
    assert events[-1][0] == "failed"
    assert events[-1][1].get("error")


def test_neoforge_download_installer_bytes_monotonic(tmp_path, monkeypatch):
    from backend.server.installer.neoforge import NeoForgeInstaller
    inst = NeoForgeInstaller(tmp_path)

    chunks = [b"A" * 600, b"B" * 400, b"C" * 1000]
    total = sum(len(c) for c in chunks)
    payload = b"".join(chunks)
    sha1 = hashlib.sha1(payload).hexdigest()

    session = MagicMock()
    def get(url, **_):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.headers = {"Content-Length": str(total)}
        if "/api/maven/versions/releases" in url:
            resp.json.return_value = {"versions": ["21.1.228"]}
        elif url.endswith(".jar"):
            resp.iter_content = lambda chunk_size: iter(chunks)
            resp.__enter__ = lambda s: s
            resp.__exit__ = lambda *a: False
        elif url.endswith(".sha1"):
            resp.text = sha1
        return resp
    session.get.side_effect = get
    inst.session = session

    def fake_run(cmd, **kwargs):
        target = tmp_path / "libraries" / "net" / "neoforged" / "neoforge" / "21.1.228"
        target.mkdir(parents=True, exist_ok=True)
        (target / "unix_args.txt").write_text("# args\n")
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")
    monkeypatch.setattr("backend.server.installer.neoforge.subprocess.run", fake_run)
    monkeypatch.setattr("backend.server.installer.neoforge.is_windows", lambda: False)

    events = []
    result = inst.install("1.21.1", progress_callback=_record(events))
    assert result.success is True

    dl = [e for e in events if e[0] == "downloading_installer"]
    assert len(dl) >= 3
    bytes_done = [e[1]["bytes_done"] for e in dl]
    assert bytes_done == sorted(bytes_done)
    assert bytes_done[-1] == total


# ----- Forge -----

def test_forge_install_emits_phases_in_order(tmp_path, monkeypatch):
    from backend.server.installer.forge import ForgeInstaller
    inst = ForgeInstaller(tmp_path)

    bytes_payload = b"PKforge"
    session = MagicMock()
    def get(url, **_):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.headers = {"Content-Length": str(len(bytes_payload))}
        if "promotions_slim.json" in url:
            resp.json.return_value = {"promos": {
                "1.20.1-recommended": "47.4.10",
                "1.20.1-latest": "47.4.20",
            }}
        elif url.endswith(".jar"):
            resp.iter_content = lambda chunk_size: iter([bytes_payload])
            resp.__enter__ = lambda s: s
            resp.__exit__ = lambda *a: False
        elif url.endswith(".sha1"):
            resp.text = hashlib.sha1(bytes_payload).hexdigest()
        return resp
    session.get.side_effect = get
    inst.session = session

    def fake_run(cmd, **kwargs):
        target = tmp_path / "libraries" / "net" / "minecraftforge" / "forge" / "1.20.1-47.4.10"
        target.mkdir(parents=True, exist_ok=True)
        (target / "unix_args.txt").write_text("# args\n")
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")
    monkeypatch.setattr("backend.server.installer.forge.subprocess.run", fake_run)
    monkeypatch.setattr("backend.server.installer.forge.is_windows", lambda: False)

    events = []
    result = inst.install("1.20.1", progress_callback=_record(events))
    assert result.success is True

    phases = _phases(events)
    expected_subset = [
        "starting", "resolving_versions", "downloading_installer",
        "verifying", "running_installer", "detecting_artifacts",
        "writing_eula", "done",
    ]
    last_idx = -1
    for needed in expected_subset:
        idx = phases.index(needed) if needed in phases else -1
        assert idx > last_idx, f"phase {needed!r} missing or out of order in {phases!r}"
        last_idx = idx


def test_forge_install_failure_emits_failed(tmp_path):
    from backend.server.installer.forge import ForgeInstaller
    inst = ForgeInstaller(tmp_path)
    import requests
    session = MagicMock()
    session.get.side_effect = requests.RequestException("forge api dead")
    inst.session = session

    events = []
    result = inst.install("1.20.1", progress_callback=_record(events))
    assert result.success is False
    assert events[-1][0] == "failed"
    assert events[-1][1].get("error")


def test_forge_download_installer_bytes_monotonic(tmp_path, monkeypatch):
    from backend.server.installer.forge import ForgeInstaller
    inst = ForgeInstaller(tmp_path)

    chunks = [b"A" * 1024, b"B" * 1024, b"C" * 512]
    total = sum(len(c) for c in chunks)
    payload = b"".join(chunks)
    sha1 = hashlib.sha1(payload).hexdigest()

    session = MagicMock()
    def get(url, **_):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.headers = {"Content-Length": str(total)}
        if "promotions_slim.json" in url:
            resp.json.return_value = {"promos": {"1.20.1-recommended": "47.4.10"}}
        elif url.endswith(".jar"):
            resp.iter_content = lambda chunk_size: iter(chunks)
            resp.__enter__ = lambda s: s
            resp.__exit__ = lambda *a: False
        elif url.endswith(".sha1"):
            resp.text = sha1
        return resp
    session.get.side_effect = get
    inst.session = session

    def fake_run(cmd, **kwargs):
        target = tmp_path / "libraries" / "net" / "minecraftforge" / "forge" / "1.20.1-47.4.10"
        target.mkdir(parents=True, exist_ok=True)
        (target / "unix_args.txt").write_text("# args\n")
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")
    monkeypatch.setattr("backend.server.installer.forge.subprocess.run", fake_run)
    monkeypatch.setattr("backend.server.installer.forge.is_windows", lambda: False)

    events = []
    result = inst.install("1.20.1", progress_callback=_record(events))
    assert result.success is True

    dl = [e for e in events if e[0] == "downloading_installer"]
    assert len(dl) >= 3
    bytes_done = [e[1]["bytes_done"] for e in dl]
    assert bytes_done == sorted(bytes_done)
    assert bytes_done[-1] == total


# ----- Backward-compat: callback=None must still work for every loader -----

def test_callback_none_does_not_crash_any_loader(tmp_path, monkeypatch):
    """Existing call sites without callback must remain working."""
    # Smoke-test for fabric only — the backward-compat plumbing was
    # already pinned in T1 via the signature anchor test. This belt-and-
    # suspenders test confirms that running install() with NO callback
    # doesn't try to dereference None somewhere.
    from backend.server.installer.fabric import FabricInstaller
    inst = FabricInstaller(tmp_path)

    monkeypatch.setattr(inst, "_get_latest_loader_version", lambda mc: None)

    # No callback passed.
    result = inst.install("1.21.4")
    assert result.success is False  # version resolution fails, that's fine
    # Test passes if no exception was raised.
