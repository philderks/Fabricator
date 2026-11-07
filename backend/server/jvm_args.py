"""Parsing and validation for user-supplied JVM arguments.

``jvmArgs`` on the server record is a **user-owned** field, deliberately
separate from ``launch.jvm_args``, which installers own: the installers write
``launch`` when a server is created and rewrite it on reinstall or a modpack
switch, so user flags parked there would be silently discarded. Keeping them
apart means a user's tuning survives everything the installers do, and the
launch builder appends them *after* the installer's own args so a user flag
wins when both set the same option.

Two consumers with deliberately different strictness:

* the settings route validates on write and rejects, so bad input is caught
  where the user can see the message;
* the launch builder parses on read and never raises — it is reached by the
  server-detail probe as well as the start path, so a hand-edited record must
  not turn a page load into a 500.
"""
from __future__ import annotations

import logging
import os
import shlex
from typing import Any, List

from backend.server import storage
from backend.server.players.files import read_json_list, write_json_list

logger = logging.getLogger(__name__)

# Bounds. Generous next to a real tuning string (a heavy G1/ZGC setup runs to
# maybe 20 flags) while keeping a pasted-in wall of text out of the record.
MAX_RAW_LENGTH = 2000
MAX_ARG_COUNT = 64

# Heap is owned by the Memory setting, which renders -Xms/-Xmx. A second -Xmx
# here would win (last flag wins) and make that field quietly wrong, so it is
# refused rather than accepted-and-ignored.
_HEAP_PREFIXES = (
    "-Xmx", "-Xms",
    "-XX:MaxHeapSize", "-XX:InitialHeapSize",
)

# These select what the JVM runs. The launch builder derives them from the
# installer's LaunchSpec; overriding one here would start something other than
# the server that was installed.
_LAUNCH_TOKENS = {"-jar", "-cp", "-classpath", "--class-path", "-p", "--module-path"}


class JvmArgsError(ValueError):
    """User-facing validation failure. The message is shown in the UI."""


def _tokenize(raw: Any) -> List[str]:
    """Split `raw` into argument tokens. Raises JvmArgsError on bad quoting."""
    if raw is None:
        return []
    if isinstance(raw, (list, tuple)):
        # Already tokenized (an API caller sending a JSON array).
        return [str(item) for item in raw if str(item).strip()]
    if not isinstance(raw, str):
        raise JvmArgsError("JVM arguments must be a string")
    if not raw.strip():
        return []
    try:
        # posix=False would keep quotes in the tokens; posix mode is what a
        # shell would hand the JVM, which is what the user is picturing.
        return shlex.split(raw)
    except ValueError as exc:
        raise JvmArgsError(f"Could not parse JVM arguments: {exc}") from exc


def validate_jvm_args(raw: Any) -> List[str]:
    """Validate user input, returning the parsed tokens.

    Raises :class:`JvmArgsError` with a message meant for the user.
    """
    if isinstance(raw, str) and len(raw) > MAX_RAW_LENGTH:
        raise JvmArgsError(
            f"JVM arguments are too long ({len(raw)} characters, max {MAX_RAW_LENGTH})"
        )

    tokens = _tokenize(raw)
    if len(tokens) > MAX_ARG_COUNT:
        raise JvmArgsError(
            f"Too many JVM arguments ({len(tokens)}, max {MAX_ARG_COUNT})"
        )

    for token in tokens:
        if token.startswith("@"):
            raise JvmArgsError(
                f"'{token}' is not allowed: argument files are set by the installer"
            )
        if token in _LAUNCH_TOKENS:
            raise JvmArgsError(
                f"'{token}' is not allowed: it would replace the server the "
                "installer set up"
            )
        for prefix in _HEAP_PREFIXES:
            if token.startswith(prefix):
                raise JvmArgsError(
                    f"'{token}' is not allowed: set the heap with the Memory "
                    "setting instead, or it would silently disagree with it"
                )
    return tokens


def parse_jvm_args(raw: Any, server_id: Any = None) -> List[str]:
    """Parse for the launch builder. Never raises.

    Anything invalid was hand-edited into the record (the write path validates),
    so it is logged and dropped: the alternative is an exception on a read path
    that also serves the server-detail page.
    """
    try:
        return validate_jvm_args(raw)
    except JvmArgsError as exc:
        logger.warning(
            "server %s: ignoring invalid jvmArgs in record (%s)",
            server_id if server_id is not None else "<unknown>", exc,
        )
        return []


def validate_java_path(raw: Any) -> str:
    """Validate a ``javaPath`` override, returning the normalized value.

    A bare command name (``java``, ``java21``) is resolved on PATH at launch and
    cannot be checked here, so it is accepted as-is. Anything that looks like a
    path is checked now — an unstartable server is much harder to diagnose from
    the failure than from this message.
    """
    if raw is None:
        return ""
    if not isinstance(raw, str):
        raise JvmArgsError("Java path must be a string")
    value = raw.strip()
    if not value:
        return ""

    looks_like_path = os.sep in value or "/" in value
    if looks_like_path:
        if os.path.isdir(value):
            raise JvmArgsError(
                f"'{value}' is a directory — point this at the java executable "
                "inside it (bin/java)"
            )
        if not os.path.isfile(value):
            raise JvmArgsError(f"No such java executable: '{value}'")
        if not os.access(value, os.X_OK):
            raise JvmArgsError(f"Not executable: '{value}'")
    return value


# --------------------------------------------------------------------------- #
# Presets (#108): named flag sets shared by every server
# --------------------------------------------------------------------------- #
#
# Stored next to servers.json rather than on a record, so a tuning string set up
# once is offered on every server. A preset is only something the UI copies
# from: applying one writes that server's own ``jvmArgs`` through the settings
# route, so editing or deleting a preset never changes a server.

PRESETS_FILE = "jvm-presets.json"
MAX_PRESETS = 50
MAX_PRESET_NAME_LENGTH = 64


def validate_presets(raw: Any) -> List[dict]:
    """Validate a whole preset list, returning it as stripped ``{name, args}``.

    Each preset's flags get the same checks as a server's ``jvmArgs``, so
    applying one can never be refused at save time. Raises
    :class:`JvmArgsError` with a message meant for the user.
    """
    if not isinstance(raw, list):
        raise JvmArgsError("Presets must be a list")
    if len(raw) > MAX_PRESETS:
        raise JvmArgsError(f"Too many presets ({len(raw)}, max {MAX_PRESETS})")

    presets: List[dict] = []
    seen = set()
    for item in raw:
        if not isinstance(item, dict):
            raise JvmArgsError("Each preset needs a name and JVM arguments")
        name = item.get("name")
        name = name.strip() if isinstance(name, str) else ""
        if not name:
            raise JvmArgsError("Every preset needs a name")
        if len(name) > MAX_PRESET_NAME_LENGTH:
            raise JvmArgsError(
                f"Preset names can be at most {MAX_PRESET_NAME_LENGTH} characters"
            )
        if name.casefold() in seen:
            raise JvmArgsError(f"There is already a preset named '{name}'")
        seen.add(name.casefold())

        args = item.get("args")
        if not isinstance(args, str) or not args.strip():
            raise JvmArgsError(f"Preset '{name}' has no JVM arguments")
        try:
            validate_jvm_args(args)
        except JvmArgsError as exc:
            raise JvmArgsError(f"Preset '{name}': {exc}") from exc
        presets.append({"name": name, "args": args.strip()})
    return presets


def load_presets() -> List[dict]:
    """Return the saved presets; ``[]`` before the first save.

    A corrupt or invalid file raises ``ValueError`` instead of reading as empty:
    an empty read would let the next save overwrite it.
    """
    return validate_presets(read_json_list(storage.SERVERS_FILE.parent, PRESETS_FILE))


def save_presets(raw: Any) -> List[dict]:
    """Validate and store the whole list, returning what was stored."""
    # shortcut: whole-list replace, last write wins. Fine for one operator's
    # panel; move to per-preset routes if concurrent editors clobber each other.
    presets = validate_presets(raw)
    write_json_list(storage.SERVERS_FILE.parent, PRESETS_FILE, presets)
    return presets
