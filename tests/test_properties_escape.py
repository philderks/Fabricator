"""server.properties values are escaped the way Java's Properties decodes them.

Both writers used to emit ``key=value`` raw: a two-line MOTD (the create modal
has always allowed one) turned its second line into a junk key, and a raw ``§``
read as ``Â§`` on Minecraft versions that load the file as ISO-8859-1.
"""
from backend.utils.strings import escape_properties_value, unescape_properties_value


def test_escape_properties_value():
    assert escape_properties_value("§6Hi\n§bYo") == "\\u00A76Hi\\n\\u00A7bYo"
    assert escape_properties_value("a 😀") == "a \\uD83D\\uDE00"
    assert escape_properties_value(25565) == "25565"
    # Hand-typed escapes from before the editor keep their meaning...
    assert escape_properties_value("\\u00A7aOld\\nstyle") == "\\u00A7aOld\\nstyle"
    # ...every other backslash survives instead of breaking the file.
    assert escape_properties_value("C:\\users") == "C:\\\\users"
    assert escape_properties_value("ends with \\") == "ends with \\\\"
    # Only the MOTD keeps leading spaces; Java strips them everywhere else.
    assert escape_properties_value("  centered", keep_leading_space=True) == "\\  centered"
    assert escape_properties_value(" world") == " world"


def test_unescape_inverts_escape():
    for value in ["§6Hi\nYo", "wélt 😀", "C:\\users", "ends with \\", "\\o/", "a=b:c #!"]:
        assert unescape_properties_value(escape_properties_value(value)) == value
    assert unescape_properties_value("\\u00A7aOld\\nstyle") == "§aOld\nstyle"


def test_lastseen_reads_escaped_level_name(tmp_path):
    from backend.server.players import lastseen

    (tmp_path / "server.properties").write_text(f"level-name={escape_properties_value('wélt')}\n")
    assert lastseen.read_level_name(tmp_path, {"levelName": "other"}) == "wélt"


def test_two_line_motd_stays_one_property(client, app, tmp_servers_root):
    from backend.server import storage

    with app.app_context():
        sid = storage.create_server({
            "name": "motd", "version": "1.21.4", "loader": "paper",
            "port": 25941, "installPath": "motd",
        })["id"]
    (tmp_servers_root / "servers" / "motd").mkdir(parents=True, exist_ok=True)

    resp = client.put(f"/api/servers/{sid}/settings", json={"motd": "§6Line one\n§bonline-mode=false"})
    assert resp.status_code == 200, resp.get_json()

    lines = (tmp_servers_root / "servers" / "motd" / "server.properties").read_text().splitlines()
    assert [l for l in lines if l.startswith("motd=")] == ["motd=\\u00A76Line one\\n\\u00A7bonline-mode=false"]
    assert [l for l in lines if l.startswith("online-mode=")] == ["online-mode=true"]
