"""The CLI hash generator produces a verifiable hash and never echoes plaintext."""
from __future__ import annotations

from click.testing import CliRunner

from backend.auth import service


def test_cli_hash_password(monkeypatch):
    from fabricator.cli import main
    result = CliRunner().invoke(main, ["hash-password"], input="hunter2\nhunter2\n")
    assert result.exit_code == 0
    out = result.output.strip().splitlines()[-1]
    monkeypatch.setenv("FABRICATOR_AUTH_PASSWORD_HASH", out)
    assert service.verify_password("hunter2") is True
    assert "hunter2" not in result.output  # hidden input, not echoed
