"""Regex coverage for the existing stdout player-tracker.

These tests pin the behavior of ServerManager._PLAYER_JOIN_RE and
_PLAYER_LEAVE_RE — both are now load-bearing for the Players tab's online
list, not just the legacy player-count, so a silent regex regression would
break two features at once.
"""
import re

from backend.server.manager import ServerManager


JOIN = ServerManager._PLAYER_JOIN_RE
LEAVE = ServerManager._PLAYER_LEAVE_RE


def test_vanilla_join_line_matches():
    line = "[12:34:56] [Server thread/INFO]: Linus joined the game"
    m = JOIN.search(line)
    assert m is not None
    assert m.group(1) == "Linus"


def test_vanilla_leave_line_matches():
    line = "[12:35:10] [Server thread/INFO]: Linus left the game"
    m = LEAVE.search(line)
    assert m is not None
    assert m.group(1) == "Linus"


def test_paper_join_line_matches():
    # Paper uses the same vanilla format — pinned as a regression test.
    line = "[12:34:56] [Server thread/INFO]: Notch joined the game"
    assert JOIN.search(line) is not None


def test_join_ignores_chat_message_with_trailing_text():
    # Chat is logged as "<name> <text>"; a message that merely contains the
    # keyword must NOT register a join (this used to spoof the online list).
    line = "[12:34:56] [Server thread/INFO]: <Griefer> haha I just joined the game"
    assert JOIN.search(line) is None


def test_join_ignores_chat_message_exactly_ending_in_keyword():
    # Even a chat line whose text is exactly "joined the game" must be ignored —
    # the "<...>" chat prefix is the discriminator.
    line = "[12:34:56] [Server thread/INFO]: <Griefer> joined the game"
    assert JOIN.search(line) is None


def test_leave_ignores_chat_message_ending_in_keyword():
    line = "[12:34:56] [Server thread/INFO]: <Griefer> rage quit and left the game"
    assert LEAVE.search(line) is None


def test_join_ignores_unsigned_chat_not_secure_prefix():
    # Minecraft 1.19+ logs unsigned chat with a "[Not Secure]" prefix before the
    # "<name>" wrapper — the "[" must not slip past the guard.
    line = "[12:34:56] [Server thread/INFO]: [Not Secure] <Griefer> I just joined the game"
    assert JOIN.search(line) is None


def test_join_matches_line_with_trailing_whitespace():
    # The end-anchor tolerates a trailing newline / whitespace on the buffered
    # line so a real join isn't dropped.
    line = "[12:34:56] [Server thread/INFO]: Notch joined the game\n"
    m = JOIN.search(line)
    assert m is not None
    assert m.group(1) == "Notch"


def test_join_allows_name_with_space():
    # Bedrock/Geyser gamertags can contain spaces; a real join line has no chat
    # "<...>" wrapper, so these must still register (a "\S+" tightening would
    # wrongly drop them).
    line = "[12:34:56] [Server thread/INFO]: Cool Gamer joined the game"
    m = JOIN.search(line)
    assert m is not None
    assert m.group(1) == "Cool Gamer"


def test_underscores_in_name_match():
    line = "[12:34:56] [Server thread/INFO]: Some_Player joined the game"
    assert JOIN.search(line).group(1) == "Some_Player"


def test_join_ignores_embedded_info_prefix_spoof():
    # A player types "INFO]: Ghost joined the game" into chat. The prefix is
    # pinned to the line start, so it can't re-anchor onto the embedded marker.
    line = "[12:34:56] [Server thread/INFO]: <Griefer> INFO]: Ghost joined the game"
    assert JOIN.search(line) is None


def test_leave_ignores_embedded_info_prefix_spoof():
    line = "[12:34:56] [Server thread/INFO]: <Griefer> INFO]: Notch left the game"
    assert LEAVE.search(line) is None


def test_join_ignores_embedded_bracketed_info_prefix_spoof():
    # Same attack, but the player includes the brackets: "[x/INFO]: ...".
    line = "[12:34:56] [Server thread/INFO]: <Griefer> [x/INFO]: Ghost joined the game"
    assert JOIN.search(line) is None


def test_join_matches_legacy_single_bracket_format():
    # Legacy Bukkit/Spigot/Paper console layout uses a single bracket:
    # "[HH:MM:SS INFO]: ...".
    line = "[12:34:56 INFO]: Notch joined the game"
    m = JOIN.search(line)
    assert m is not None
    assert m.group(1) == "Notch"


def test_join_ignores_spoof_in_single_bracket_format():
    line = "[12:34:56 INFO]: <Griefer> INFO]: Ghost joined the game"
    assert JOIN.search(line) is None


def test_join_matches_forge_style_category_line():
    # Forge/NeoForge add a "[category]" between the thread marker and the colon.
    line = "[12:34:56] [Server thread/INFO] [minecraft/MinecraftServer]: Notch joined the game"
    m = JOIN.search(line)
    assert m is not None
    assert m.group(1) == "Notch"


def test_join_matches_ansi_wrapped_name_after_strip():
    # Some setups colour the name on the pipe; _stream strips ANSI before match.
    from backend.server.manager import ServerManager
    raw = "[12:34:56] [Server thread/INFO]: \x1b[37mNotch\x1b[m joined the game"
    clean = ServerManager._ANSI_RE.sub("", raw)
    m = JOIN.search(clean)
    assert m is not None
    assert m.group(1) == "Notch"
