"""The backend auth module hash generator produces a verifiable hash."""
from __future__ import annotations

from backend.auth import service


def test_module_hash(monkeypatch, capsys):
    import backend.auth.__main__ as entry

    monkeypatch.setattr("getpass.getpass", lambda *a, **k: "hunter2")
    rc = entry.main(["hash"])
    assert rc == 0
    out = capsys.readouterr().out.strip().splitlines()[-1]
    monkeypatch.setenv("FABRICATOR_AUTH_PASSWORD_HASH", out)
    assert service.verify_password("hunter2") is True
