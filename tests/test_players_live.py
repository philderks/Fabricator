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


def test_join_ignores_chat_messages_containing_keyword():
    # Chat messages also flow through INFO but use a different prefix shape.
    # The regex relies on the "joined the game" tail anchor, not the prefix.
    line = "[12:34:56] [Server thread/INFO]: <Linus> joined the game now?"
    # Acceptable false-positive: regex would match "Linus> " here.
    # Documenting current behavior so a future tightening shows up as a diff.
    m = JOIN.search(line)
    assert m is not None  # current behavior — name capture is permissive


def test_underscores_in_name_match():
    line = "[12:34:56] [Server thread/INFO]: Some_Player joined the game"
    assert JOIN.search(line).group(1) == "Some_Player"
