"""Both hash generators produce a verifiable hash and never echo plaintext."""
from __future__ import annotations

from click.testing import CliRunner

from backend.auth import service


def test_cli_hash_password(monkeypatch):
    from tools.cli import cli
    result = CliRunner().invoke(cli, ["hash-password"], input="hunter2\nhunter2\n")
    assert result.exit_code == 0
    out = result.output.strip().splitlines()[-1]
    monkeypatch.setenv("FABRICATOR_AUTH_PASSWORD_HASH", out)
    assert service.verify_password("hunter2") is True
    assert "hunter2" not in result.output  # hidden input, not echoed


def test_module_hash(monkeypatch, capsys):
    import backend.auth.__main__ as entry
    monkeypatch.setattr("getpass.getpass", lambda *a, **k: "hunter2")
    rc = entry.main(["hash"])
    assert rc == 0
    out = capsys.readouterr().out.strip().splitlines()[-1]
    monkeypatch.setenv("FABRICATOR_AUTH_PASSWORD_HASH", out)
    assert service.verify_password("hunter2") is True
