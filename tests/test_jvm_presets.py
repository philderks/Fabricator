"""JVM flag presets (#108): named flag sets shared by every server.

Stored whole in jvm-presets.json next to servers.json. Each preset's flags get
the same checks as a server's own jvmArgs, so applying one can never be refused
when that server's settings are saved.
"""
from __future__ import annotations

import json

import pytest

URL = "/api/jvm-presets"
G1 = "-XX:+UseG1GC -XX:MaxGCPauseMillis=200"


def test_fresh_install_has_no_presets(client):
    resp = client.get(URL)
    assert resp.status_code == 200
    assert resp.get_json() == {"presets": []}


def test_put_replaces_the_list_and_persists(client, tmp_servers_root):
    resp = client.put(URL, json={"presets": [{"name": "  G1 tune ", "args": f"  {G1} "}]})
    assert resp.status_code == 200
    saved = [{"name": "G1 tune", "args": G1}]
    assert resp.get_json() == {"presets": saved}
    assert client.get(URL).get_json() == {"presets": saved}
    assert json.loads((tmp_servers_root / "jvm-presets.json").read_text()) == saved

    # Whole-list replace: an empty list deletes everything.
    assert client.put(URL, json={"presets": []}).get_json() == {"presets": []}
    assert client.get(URL).get_json() == {"presets": []}


def test_flags_get_the_jvm_args_checks_and_a_bad_save_changes_nothing(client):
    client.put(URL, json={"presets": [{"name": "G1 tune", "args": G1}]})

    resp = client.put(URL, json={"presets": [{"name": "Big", "args": "-XX:+UseG1GC -Xmx4G"}]})
    assert resp.status_code == 400
    error = resp.get_json()["error"]
    assert "Preset 'Big'" in error and "Memory setting" in error
    assert client.get(URL).get_json() == {"presets": [{"name": "G1 tune", "args": G1}]}


@pytest.mark.parametrize("body", [
    {},
    [{"name": "Not wrapped", "args": G1}],
    {"presets": "not a list"},
    {"presets": ["not an object"]},
    {"presets": [{"name": "  ", "args": G1}]},
    {"presets": [{"name": "x" * 65, "args": G1}]},
    {"presets": [{"name": "Tune", "args": G1}, {"name": "tune", "args": G1}]},
    {"presets": [{"name": "Empty", "args": "  "}]},
    {"presets": [{"name": "Tokens", "args": ["-XX:+UseG1GC"]}]},
    {"presets": [{"name": f"p{i}", "args": G1} for i in range(51)]},
])
def test_invalid_lists_are_rejected(client, body):
    resp = client.put(URL, json=body)
    assert resp.status_code == 400
    assert resp.get_json()["error"]


def test_a_non_json_body_is_rejected(client):
    assert client.put(URL, data="nope", content_type="text/plain").status_code == 400


def test_a_corrupt_file_is_an_error_not_an_empty_list(client, tmp_servers_root):
    (tmp_servers_root / "jvm-presets.json").write_text("{not json", encoding="utf-8")
    resp = client.get(URL)
    assert resp.status_code == 500
    assert resp.get_json()["error"]
