"""Minecraft server management service."""
import logging
import os
import re
import subprocess
import threading
import time
from typing import Iterable, List, Optional

from backend.server import tps as tps_probe
from backend.utils import platform as platform_utils
from backend.utils.java import parse_java_major
from backend.utils.time import iso_z_now
try:
    import psutil  # type: ignore
except ImportError:  # pragma: no cover - optional dependency fallback
    psutil = None


logger = logging.getLogger(__name__)


from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict


@dataclass
class OnlinePlayer:
    """Represents a player currently connected to a running server.

    `uuid` is populated lazily by the players service when /online is served —
    the stdout-stream loop only sees names and must not block on HTTP lookups.
    """
    name: str
    joined_at: datetime
    uuid: Optional[str] = None


class ServerManager:
    """Manages the lifecycle of a Minecraft server process."""

    DEFAULT_COMMAND = "java -Xmx2G -jar server.jar nogui"
    MAX_LOG_LINES = 10_000
    # How much of the previous run's tail stays visible after a restart. The
    # console is where a crash gets diagnosed, and restarting to recover used to
    # wipe exactly the output that explained the crash.
    PREV_RUN_LINES = 500
    # Player join/leave detection from server stdout. The log prefix is pinned
    # to the START of the line — "[<timestamp>] [<thread>/INFO]" (plus Forge's
    # optional "[<category>]") — so a player who types "INFO]: Ghost joined the
    # game" (or "[x/INFO]: ...") into CHAT can't make the prefix re-anchor onto
    # that embedded marker and spoof a join/leave. The name is then restricted
    # to characters a real username can't share with the chat wrapper ("<", ">")
    # or the 1.19+ "[Not Secure]" prefix ("[", "]"), which rejects "<Notch> ..."
    # and "[Not Secure] <Notch> ..." while still allowing spaces (Bedrock/Geyser
    # gamertags). Lines are ANSI-stripped (see _ANSI_RE) before matching, so a
    # colour-wrapped name isn't dropped by the "[" exclusion.
    _LOG_PREFIX = (
        r'^(?:'
        r'\[[^\]]*INFO\]'                            # legacy single bracket: [HH:MM:SS INFO]
        r'|\[[^\]]+\] \[[^\]]*INFO\](?: \[[^\]]*\])?'  # [time] [thread/INFO] (+ Forge [category])
        r'): '
    )
    _PLAYER_JOIN_RE = re.compile(_LOG_PREFIX + r'([^<>\[\]]+) joined the game')
    _PLAYER_LEAVE_RE = re.compile(_LOG_PREFIX + r'([^<>\[\]]+) left the game')
    # SGR colour escapes some setups emit around the message on the pipe.
    _ANSI_RE = re.compile(r'\x1b\[[0-9;]*m')
    # "Done (12.345s)! For help, type "help"" — the world is loaded and the
    # console accepts commands. Same prefix anchoring as the player patterns so
    # chat cannot fake it.
    _SERVER_READY_RE = re.compile(_LOG_PREFIX + r'Done \(')
    # The prefix on its own, used to split a line into prefix + message body
    # before reading it as a TPS reply.
    _LOG_LINE_RE = re.compile(_LOG_PREFIX)

    # TPS sampling. There is no push channel for tick rate, so a background
    # thread types the loader's TPS command into the console on this interval
    # and the stdout reader picks the answer back out. 30s is deliberately
    # unhurried: Paper's figure is itself a 1-minute rolling average, so polling
    # faster would only add lines to the server's own latest.log (which we
    # cannot suppress — only Fabricator's console view is filtered) without
    # making the number any fresher.
    TPS_SAMPLE_INTERVAL_SEC = 30.0
    # How long a sample waits for its answer before being counted a miss.
    TPS_RESPONSE_TIMEOUT_SEC = 5.0
    # Consecutive misses before the sampler gives up for the rest of the run.
    # Guards against a loader that turns out not to know the command we picked:
    # better one dead stat card than an error line every interval forever.
    TPS_MAX_MISSES = 3
    # Longest wait for the "Done (" line before giving up on sampling. Generous
    # because a large modpack can genuinely take this long to load.
    TPS_READY_TIMEOUT_SEC = 900.0
    # A reading older than this is dropped rather than shown: a frozen number
    # reads as "fine" when in fact the server stopped answering. Sized to outlast
    # the sampler's full give-up sequence (TPS_MAX_MISSES rounds of interval +
    # response timeout), so a brief unresponsive patch does not blank the card
    # before the sampler itself has concluded anything.
    TPS_STALE_AFTER_SEC = 150.0

    def __init__(
        self,
        cwd: str,
        command: Optional[Iterable[str]] = None,
        loader: Optional[str] = None,
        version: Optional[str] = None,
    ):
        env_command = os.environ.get("SERVER_COMMAND")
        parsed_env_command: Optional[List[str]] = None
        if env_command:
            parsed_env_command = self._split_command(env_command)

        self.command = self._parse_command(command or parsed_env_command) or self._split_command(
            self.DEFAULT_COMMAND
        )
        self.cwd = cwd
        self._memory_limit_bytes = self._extract_memory_limit_bytes(self.command)
        self._process: Optional[subprocess.Popen] = None
        self._ps_process: Optional["psutil.Process"] = None  # type: ignore[name-defined]
        self._stdout_thread: Optional[threading.Thread] = None
        self._stderr_thread: Optional[threading.Thread] = None
        # Each entry is ``(capture_ts, text)`` where capture_ts is an ISO-Z
        # timestamp taken when Fabricator read the line. The server's own
        # ``[HH:MM:SS]`` is in the JVM's timezone (UTC on most hosts); shipping
        # an absolute capture time instead lets the frontend render it in the
        # viewer's local timezone. Appends/reads are guarded by ``_buffer_lock``
        # (below).
        self._stdout_buffer: List[tuple[str, str]] = []
        self._stderr_buffer: List[tuple[str, str]] = []
        # Tail of the previous run, carried across a restart. Deliberately kept
        # in its own pair of buffers rather than left in the live ones: the
        # immediate-exit diagnostics and wait_for_log()/_stdout_total must keep
        # seeing ONLY the current run, or a server that dies before printing
        # anything would be diagnosed from the previous run's output.
        self._prev_stdout_buffer: List[tuple[str, str]] = []
        self._prev_stderr_buffer: List[tuple[str, str]] = []
        # Monotonic count of stdout lines ever appended — never reset by the
        # MAX_LOG_LINES front-truncation. wait_for_log() diffs this instead of
        # absolute buffer indices, which stop advancing once the buffer
        # saturates at MAX_LOG_LINES and every append front-truncates.
        self._stdout_total = 0
        # Dedicated lock for the stdout/stderr buffers + _stdout_total, SEPARATE
        # from self._lock. The append and the counter bump happen together under
        # it so wait_for_log() reads a consistent (buffer, total) pair. It is NOT
        # self._lock on purpose: start() holds self._lock across _spawn_process's
        # 0.5s probe, and blocking the stream append there would empty the
        # immediate-exit diagnostic tail.
        self._buffer_lock = threading.Lock()
        self._players: Dict[str, OnlinePlayer] = {}
        # Which TPS command this server understands is decided from these two.
        # Public and re-assignable: the registry refreshes them before a start
        # exactly as it does self.command, so an upgraded server is sampled
        # with the right command without recreating the manager.
        self.loader = str(loader) if loader else None
        self.version = str(version) if version else None
        self._tps_probe: Optional[tps_probe.TpsProbe] = None
        self._tps: Optional[float] = None
        self._tps_at = 0.0  # monotonic; 0.0 = never sampled this run
        # Vanilla reports a target rate and a per-tick cost on separate lines;
        # the target from the first is what caps the rate derived from the second.
        self._tps_target_rate = tps_probe.DEFAULT_TICK_RATE
        # While monotonic() is under this deadline we are waiting on our OWN
        # probe, and the reply is suppressed from the console buffer. Outside
        # that window an identical reply is the user's own command, and stays.
        self._tps_pending_until = 0.0
        self._tps_response = threading.Event()
        self._tps_thread: Optional[threading.Thread] = None
        self._tps_stop = threading.Event()
        # Set when the current run logs "Done (" — the sampler holds off until
        # then, since a command sent mid-load only produces an error line.
        self._ready_event = threading.Event()
        self._lock = threading.Lock()
        # True only while stop() is draining a still-alive process. stop()
        # releases the lock during the drain (so stream threads can log shutdown
        # lines), which makes is_running briefly read False even though the JVM
        # is still up; start() checks this flag to avoid launching a second
        # process on the same world during that window.
        self._stopping = False

    def _parse_command(self, command: Optional[Iterable[str]]) -> Optional[List[str]]:
        if command is None:
            return None
        if isinstance(command, str):
            return self._split_command(command)
        if isinstance(command, Iterable):
            return list(command)
        return None

    @staticmethod
    def _split_command(command: str) -> List[str]:
        """Split a command string with platform-appropriate shlex settings."""
        return platform_utils.split_command(command)

    @staticmethod
    def _parse_memory_quantity(spec: str) -> Optional[int]:
        if not spec:
            return None
        spec = spec.strip()
        if not spec:
            return None
        unit = spec[-1].lower()
        multipliers = {
            'k': 1024,
            'm': 1024 ** 2,
            'g': 1024 ** 3
        }
        if unit in multipliers:
            number_part = spec[:-1]
            multiplier = multipliers[unit]
        else:
            number_part = spec
            multiplier = 1
        try:
            value = float(number_part)
        except ValueError:
            return None
        return int(value * multiplier)

    def _extract_memory_limit_bytes(self, command: Optional[List[str]]) -> Optional[int]:
        if not command:
            return None
        for part in command:
            if not isinstance(part, str):
                continue
            if part.startswith('-Xmx') and len(part) > 4:
                quantity = self._parse_memory_quantity(part[4:])
                if quantity:
                    return quantity
        return None

    def _ensure_server_dir(self) -> None:
        os.makedirs(self.cwd, exist_ok=True)

    def _ensure_eula(self) -> None:
        self._ensure_server_dir()
        eula_path = os.path.join(self.cwd, "eula.txt")
        if os.path.exists(eula_path):
            with open(eula_path, "r", encoding="utf-8") as eula_file:
                contents = eula_file.read()
            if "eula=true" in contents:
                return
        with open(eula_path, "w", encoding="utf-8") as eula_file:
            eula_file.write("eula=true\n")

    def _java_executable(self) -> str:
        if self.command and isinstance(self.command[0], str) and self.command[0].strip():
            return self.command[0]
        return "java"

    # JDK 23 (JEP 471) deprecated sun.misc.Unsafe's memory-access methods; JDK 24
    # (JEP 498) makes the JVM print a WARNING the first time one is called.
    # Minecraft's JOML math library calls them, so every modern server spams four
    # scary-looking lines on boot. This flag opts back into silent access.
    _UNSAFE_ACCESS_FLAG = "--sun-misc-unsafe-memory-access=allow"

    def _with_unsafe_suppression(self, command: List[str], java_major: int) -> List[str]:
        """Insert the Unsafe-warning suppression flag for Java 23+ launches.

        The flag only exists on Java 23 and newer; passing it to an older JVM
        aborts startup, so it is gated on the probed major version. A JVM option
        must precede ``-jar``/the main class, so it goes right after the java
        executable. Skipped if the user already set it themselves.
        """
        if java_major < 23 or not command:
            return command
        if any(
            isinstance(arg, str) and arg.startswith("--sun-misc-unsafe-memory-access")
            for arg in command
        ):
            return command
        return [command[0], self._UNSAFE_ACCESS_FLAG, *command[1:]]

    def probe_java(self) -> dict:
        java_exec = self._java_executable()
        try:
            result = subprocess.run(
                [java_exec, "-version"],
                capture_output=True,
                text=True,
                **platform_utils.subprocess_no_window_kwargs(),
            )
        except FileNotFoundError:
            return {
                "available": False,
                "java_exec": java_exec,
                "major_version": None,
                "version_output": "",
                "message": (
                    f"Java executable '{java_exec}' is not installed or not found. "
                    "Please install Java or update server Java path."
                ),
                "java_missing": True,
            }
        version_output = (result.stdout or "") + (result.stderr or "")
        if result.returncode != 0:
            return {
                "available": False,
                "java_exec": java_exec,
                "major_version": None,
                "version_output": version_output.strip(),
                "message": f"Java executable '{java_exec}' is not available",
                "java_missing": False,
            }

        major_version = parse_java_major(version_output)
        if major_version is None:
            return {
                "available": False,
                "java_exec": java_exec,
                "major_version": None,
                "version_output": version_output.strip(),
                "message": "Could not determine Java version",
                "java_missing": False,
            }

        return {
            "available": True,
            "java_exec": java_exec,
            "major_version": major_version,
            "version_output": version_output.strip(),
            "message": version_output.strip(),
            "java_missing": False,
        }

    def _start_log_streams(self) -> None:
        if not self._process:
            return

        def _stream(pipe, buffer: List[tuple[str, str]], is_stdout: bool):
            for line in iter(pipe.readline, ""):
                # Detection runs on the ANSI-stripped, prefix-anchored line (the
                # raw line stays in the buffer for the colour console viewer).
                clean = self._ANSI_RE.sub("", line)
                # Read before buffering: the reply to our own TPS probe is
                # consumed here and kept out of the console the user reads, so
                # a periodic poll does not scroll their log away. Runs outside
                # _buffer_lock — it may take self._lock to store the reading,
                # and that is the forbidden nesting order.
                suppress = is_stdout and self._consume_tps_line(clean)
                if not suppress:
                    # Append + truncate + counter bump together under
                    # _buffer_lock (NOT self._lock) so wait_for_log sees a
                    # consistent (buffer, _stdout_total) snapshot, while start()'s
                    # self._lock hold across the 0.5s spawn probe can't block this
                    # append (which would empty the immediate-exit diagnostic tail).
                    with self._buffer_lock:
                        buffer.append((iso_z_now(), line))
                        if len(buffer) > self.MAX_LOG_LINES:
                            del buffer[: len(buffer) - self.MAX_LOG_LINES]
                        if is_stdout:
                            self._stdout_total += 1
                if is_stdout and not self._ready_event.is_set() and self._SERVER_READY_RE.search(clean):
                    self._ready_event.set()
                join_match = self._PLAYER_JOIN_RE.search(clean)
                if join_match:
                    name = join_match.group(1)
                    with self._lock:
                        self._players[name] = OnlinePlayer(
                            name=name,
                            joined_at=datetime.now(timezone.utc),
                        )
                else:
                    leave_match = self._PLAYER_LEAVE_RE.search(clean)
                    if leave_match:
                        with self._lock:
                            self._players.pop(leave_match.group(1), None)
                if not suppress:
                    print(line, end="")
            pipe.close()

        with self._buffer_lock:
            # Demote the finished run's tail instead of dropping it, so a
            # restart no longer erases the output that prompted the restart.
            self._prev_stdout_buffer = self._stdout_buffer[-self.PREV_RUN_LINES:]
            self._prev_stderr_buffer = self._stderr_buffer[-self.PREV_RUN_LINES:]
            self._stdout_buffer = []
            self._stderr_buffer = []
            self._stdout_total = 0
        # Belongs to the run, like the buffers: cleared before the stream threads
        # that set it are started.
        self._ready_event.clear()
        self._stdout_thread = threading.Thread(
            target=_stream, args=(self._process.stdout, self._stdout_buffer, True), daemon=True
        )
        self._stderr_thread = threading.Thread(
            target=_stream, args=(self._process.stderr, self._stderr_buffer, False), daemon=True
        )
        self._stdout_thread.start()
        self._stderr_thread.start()

    def _consume_tps_line(self, clean: str) -> bool:
        """Read a stdout line as a possible TPS reply. True means "don't log it".

        Suppression is deliberately narrow: only a reply arriving inside the
        window of a probe *we* sent is hidden. The same output produced by a
        user typing the command themselves stays in their console — and is still
        harvested as a free sample.
        """
        if self._tps_probe is None:
            return False

        prefix = self._LOG_LINE_RE.match(clean)
        if prefix:
            body = clean[prefix.end():]
            if body[:1] in ("<", "["):
                # Chat, including the 1.19+ "[Not Secure]" marker. Same reasoning
                # as the player patterns: a player typing "TPS from last 1m..."
                # must not be able to write a fake tick rate onto the dashboard.
                return False
        else:
            # A line with no log prefix at all. Vanilla's /tick query reply is a
            # single multi-line chat component, so log4j stamps only its first
            # line and the rest — including "Average time per tick", the one line
            # carrying the number — arrives bare. Accepting these is what makes
            # vanilla/Fabric/Quilt work at all, and it does not reopen the
            # spoofing hole above: chat is always logged WITH a prefix, and
            # Minecraft does not let a player put a newline in a message, so a
            # bare line cannot be player-authored.
            body = clean
        reading = tps_probe.classify(body)
        if reading is None:
            return False

        kind, value = reading
        # The window expires on its own rather than being cleared by the first
        # matching line: vanilla answers over three lines, and the trailing
        # percentile line would otherwise escape into the console.
        pending = time.monotonic() < self._tps_pending_until

        if kind == tps_probe.TARGET_RATE:
            self._tps_target_rate = value
            return pending
        if kind == tps_probe.NOISE:
            return pending
        if kind == tps_probe.MSPT:
            value = tps_probe.rate_from_mspt(value, self._tps_target_rate)

        with self._lock:
            self._tps = value
            self._tps_at = time.monotonic()
        self._tps_response.set()
        return pending

    def _wait_until_ready(self) -> bool:
        """Block until the run logs "Done (", or the run/patience ends."""
        deadline = time.monotonic() + self.TPS_READY_TIMEOUT_SEC
        while not self._ready_event.is_set():
            if self._tps_stop.wait(0.5):
                return False
            if time.monotonic() > deadline:
                return False
        return True

    def _tps_sampler(self, probe: "tps_probe.TpsProbe") -> None:
        """Type the loader's TPS command into the console on a fixed interval.

        Held back until the world has loaded, because a command sent mid-load
        only produces an error line, and abandoned after TPS_MAX_MISSES silent
        rounds so a wrong guess about the loader costs one blank stat card
        rather than an error every interval for the life of the server.
        """
        if not self._wait_until_ready():
            return

        misses = 0
        while not self._tps_stop.wait(self.TPS_SAMPLE_INTERVAL_SEC):
            if not self.is_running:
                return

            self._tps_response.clear()
            self._tps_pending_until = time.monotonic() + self.TPS_RESPONSE_TIMEOUT_SEC
            result = self.send_command(probe.command)
            if not result.get("success"):
                # Process gone or stdin closed; there is nothing left to ask.
                return

            answered = self._tps_response.wait(self.TPS_RESPONSE_TIMEOUT_SEC)
            if self._tps_stop.is_set():
                # stop() sets the response event too, so the shutdown path never
                # waits out the full response timeout for this thread to notice.
                return
            if answered:
                misses = 0
                continue

            misses += 1
            if misses >= self.TPS_MAX_MISSES:
                logger.info(
                    "Server in %s did not answer %r; TPS sampling off for this run",
                    self.cwd,
                    probe.command,
                )
                return

    def _start_tps_sampler(self) -> None:
        """Begin sampling, if this loader/version can answer at all."""
        self._tps = None
        self._tps_at = 0.0
        self._tps_target_rate = tps_probe.DEFAULT_TICK_RATE
        self._tps_pending_until = 0.0
        self._tps_stop.clear()
        self._tps_response.clear()

        probe = tps_probe.probe_for(self.loader, self.version)
        self._tps_probe = probe
        if probe is None:
            return

        thread = threading.Thread(
            target=self._tps_sampler, args=(probe,), daemon=True
        )
        self._tps_thread = thread
        thread.start()

    def _spawn_process(self, command_to_run: List[str]) -> tuple[bool, str]:
        try:
            self._process = subprocess.Popen(
                command_to_run,
                cwd=self.cwd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                **platform_utils.subprocess_no_window_kwargs(),
            )
            self._ps_process = None
            self._start_log_streams()
            time.sleep(0.5)

            if self._process.poll() is not None:
                exit_code = self._process.returncode
                stdout_tail = "".join(text for _, text in self._stdout_buffer[-10:])
                stderr_tail = "".join(text for _, text in self._stderr_buffer[-10:])
                self._process = None
                error_message = f"Server process exited immediately (code {exit_code})."
                if stdout_tail:
                    error_message += f" stdout: {stdout_tail.strip()}"
                if stderr_tail:
                    error_message += f" stderr: {stderr_tail.strip()}"
                return False, error_message

            self._start_tps_sampler()
            return True, "Server started"
        except Exception as exc:
            logger.exception("Failed to start server process")
            self._process = None
            return False, f"Failed to start server: {exc}"

    def start(self, required_java_major: Optional[int] = None) -> dict:
        """Start the server process if it is not already running."""
        with self._lock:
            if self.is_running:
                return {"status": "running", "message": "Server is already running"}

            if self._stopping:
                # A stop() is draining a still-alive JVM (is_running reads False
                # only because self._process was cleared). Launching now would
                # put a second process on the same world → corruption. The
                # "stopping" marker lets the route reject without clobbering the
                # persisted "stopping" status back to "stopped" mid-drain.
                return {
                    "status": "stopped",
                    "stopping": True,
                    "message": "Server is still stopping; wait for it to fully stop before starting again",
                }

            command_to_run = self.command

            if not command_to_run:
                return {
                    "status": "stopped",
                    "message": "No server command configured. Set SERVER_COMMAND or pass a command list.",
                }

            self._ensure_eula()
            java_info = self.probe_java()
            if not java_info.get("available"):
                return {
                    "status": "stopped",
                    "message": java_info.get("message", "Java executable not available"),
                    "java_missing": bool(java_info.get("java_missing", False)),
                    "server_java_target": java_info.get("java_exec"),
                }

            detected_java = int(java_info.get("major_version"))
            if required_java_major is not None and detected_java < required_java_major:
                return {
                    "status": "stopped",
                    "message": (
                        f"Java {required_java_major}+ is required "
                        f"(found Java {detected_java})"
                    ),
                    "java_missing": False,
                    "java_too_old": True,
                    "required_java": required_java_major,
                    "detected_java": detected_java,
                    "server_java_target": java_info.get("java_exec"),
                }

            command_to_run = self._with_unsafe_suppression(command_to_run, detected_java)
            started, message = self._spawn_process(command_to_run)
            status = "running" if started else "stopped"
            combined_message = message
            if started:
                combined_message = f"{message} (Java verified: {java_info.get('message', '')})"

            return {
                "status": status,
                "message": combined_message,
                "command": command_to_run,
                "detected_java": detected_java,
                "server_java_target": java_info.get("java_exec"),
            }

    def stop(self) -> dict:
        """Stop the server process if it is running."""
        with self._lock:
            if not self.is_running or not self._process:
                return {"status": "stopped", "message": "Server is not running"}

            proc = self._process
            stdout_thread = self._stdout_thread
            stderr_thread = self._stderr_thread
            tps_thread = self._tps_thread
            self._process = None
            self._ps_process = None
            self._players.clear()
            self._stdout_thread = None
            self._stderr_thread = None
            self._tps_thread = None
            self._tps_probe = None
            self._tps = None
            self._tps_at = 0.0
            # Both events: _tps_stop is the actual signal, _tps_response only
            # wakes the sampler out of its response wait so the join below is
            # immediate rather than up to TPS_RESPONSE_TIMEOUT_SEC.
            self._tps_stop.set()
            self._tps_response.set()
            # Set atomically with clearing self._process so start() (which needs
            # the same lock) sees a consistent state: either the process is still
            # present (is_running True) or _stopping is True — never a window
            # where both look idle. Reset in the finally once the drain is done.
            self._stopping = True

        # Lock released so stream threads can still acquire it while draining
        # shutdown log lines (e.g. player-disconnect events logged on shutdown).
        try:
            if proc.stdin and not proc.stdin.closed:
                try:
                    proc.stdin.write("stop\n")
                    proc.stdin.flush()
                except Exception:
                    logger.warning(
                        "Failed to write 'stop' command to server stdin",
                        exc_info=True,
                    )

            proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    pass
        finally:
            if stdout_thread:
                stdout_thread.join(timeout=5)
            if stderr_thread:
                stderr_thread.join(timeout=5)
            if tps_thread:
                tps_thread.join(timeout=5)
            with self._lock:
                self._stopping = False

        return {"status": "stopped", "message": "Server stopped"}

    @property
    def is_running(self) -> bool:
        return bool(self._process and self._process.poll() is None)

    def status(self) -> dict:
        running = self.is_running
        status_value = "running" if running else "stopped"
        message = "Server process is running" if running else "Server process is not running"
        ram_usage = self._get_ram_usage_bytes()
        ram_limit = self._memory_limit_bytes
        status = {"status": status_value, "message": message}
        if ram_usage is not None or ram_limit is not None:
            ram_info = {}
            if ram_usage is not None:
                ram_info["usedBytes"] = ram_usage
                ram_info["usedMB"] = round(ram_usage / (1024 ** 2), 2)
                ram_info["usedGB"] = round(ram_usage / (1024 ** 3), 3)
            if ram_limit is not None:
                ram_info["limitBytes"] = ram_limit
                ram_info["limitMB"] = round(ram_limit / (1024 ** 2), 2)
                ram_info["limitGB"] = round(ram_limit / (1024 ** 3), 3)
            status["ram"] = ram_info
        cpu_percent = self._get_cpu_percent()
        if cpu_percent is not None:
            status["cpu"] = cpu_percent
            # Ship the host core count so the UI can render either the raw
            # total or the per-core average without a second round-trip.
            cores = psutil.cpu_count() if psutil else None
            if cores:
                status["cpuCores"] = cores
        if self._process and running:
            status["pid"] = self._process.pid
        with self._lock:
            if not running:
                self._players.clear()
            status["players"] = {"online": len(self._players)}
            tps_value = self._tps
            tps_at = self._tps_at
        if running:
            # Whether this server can report a tick rate at all, so the UI can
            # say "n/a" for an old vanilla/Fabric server instead of showing a
            # perpetual "—" that looks like a bug.
            status["tpsSupported"] = self._tps_probe is not None
            # A stale reading is dropped rather than frozen on screen: a number
            # that stopped updating still reads as "the server is fine".
            if (
                tps_value is not None
                and tps_at
                and (time.monotonic() - tps_at) <= self.TPS_STALE_AFTER_SEC
            ):
                status["tps"] = round(tps_value, 2)
        return status

    @staticmethod
    def _serialize_run_tail(
        previous: List[tuple[str, str]],
        current: List[tuple[str, str]],
        limit: int,
        boundary: bool = False,
    ) -> List[dict]:
        """Previous run's tail, an optional restart marker, then the current run.

        ``boundary`` is set for stdout only — emitting it on both streams would
        render two dividers in a console that interleaves them. The marker
        borrows the first current-run timestamp (falling back to the last
        previous-run one) so it stays sortable: the frontend only interleaves
        stdout and stderr when EVERY line has a parseable ts, and a null here
        would silently drop it back to stdout-then-stderr ordering.

        Once the current run alone fills ``limit`` the older lines and the
        marker fall off the front on their own.
        """
        if limit <= 0:
            return []
        entries: List[dict] = [{"ts": ts, "text": text} for ts, text in previous]
        if boundary and previous:
            marker_ts = current[0][0] if current else previous[-1][0]
            entries.append({"ts": marker_ts, "text": "Server restarted", "boundary": True})
        entries.extend({"ts": ts, "text": text} for ts, text in current)
        return entries[-limit:]

    def tail_logs(self, limit: int = 1000) -> dict:
        # Buffers are guarded by _buffer_lock (the writer's lock), not _lock.
        with self._buffer_lock:
            stdout = self._serialize_run_tail(
                self._prev_stdout_buffer, self._stdout_buffer, limit, boundary=True
            )
            stderr = self._serialize_run_tail(
                self._prev_stderr_buffer, self._stderr_buffer, limit
            )
        # Taken separately, never nested inside _buffer_lock: the stream thread
        # releases _buffer_lock before acquiring _lock for player tracking, and
        # nesting them the other way round here would invert that order.
        with self._lock:
            running = self.is_running
        return {"stdout": stdout, "stderr": stderr, "running": running}

    def wait_for_log(
        self,
        pattern: "re.Pattern[str] | str",
        timeout: float = 60.0,
        poll_interval: float = 0.1,
    ) -> bool:
        """Wait for a log line matching ``pattern`` to appear after now.

        Snapshots the monotonic stdout line counter under the lock, then polls
        every ``poll_interval`` seconds for any newly-appended stdout line that
        matches. Lines already in the buffer at call time are ignored — callers
        want confirmation of an action they just triggered (e.g. ``save-all
        flush``), not the historical state.

        Uses ``self._stdout_total`` (a count that survives the MAX_LOG_LINES
        front-truncation) rather than absolute buffer indices: once the buffer
        saturates, its length stops growing, so an absolute ``start_index``
        would never be exceeded and this would always time out.

        The counter read and the buffer slice are taken together under
        ``_buffer_lock`` (the same lock _stream appends under) so an interleaved
        append cannot shift the tail window and make ``seen_total`` skip an
        unseen line. Returns True on match, False on timeout. Uses
        ``time.monotonic`` so a wall-clock jump (NTP adjust, suspend/resume)
        doesn't extend or truncate the wait.
        """
        if isinstance(pattern, str):
            pattern = re.compile(pattern)

        def _drain_new(seen_total: int):
            """Return (new lines since seen_total, updated total). Best-effort:
            if more than MAX_LOG_LINES arrived between polls, only the retained
            tail is returned. Counter + slice are read atomically under
            _buffer_lock; the returned slice is a fresh copy safe to iterate
            after release."""
            with self._buffer_lock:
                total = self._stdout_total
                new = total - seen_total
                pending = self._stdout_buffer[-new:] if new > 0 else []
            return pending, total

        with self._buffer_lock:
            seen_total = self._stdout_total

        deadline = time.monotonic() + max(0.0, timeout)
        while time.monotonic() < deadline:
            pending, seen_total = _drain_new(seen_total)
            for _, line in pending:
                if pattern.search(line):
                    return True
            time.sleep(poll_interval)

        # One final sweep — covers the race where the matching line arrives
        # after the last poll-sleep but before timeout.
        pending, _ = _drain_new(seen_total)
        for _, line in pending:
            if pattern.search(line):
                return True
        return False

    def send_command(self, command: str) -> dict:
        """Send a console command to the running server process."""
        if not command.strip():
            return {"success": False, "message": "Command must not be empty"}

        with self._lock:
            if not self.is_running or not self._process:
                return {"success": False, "message": "Server is not running"}

            stdin = self._process.stdin
            if not stdin or stdin.closed:
                return {"success": False, "message": "Server stdin is not available"}

            try:
                stdin.write(command.strip() + "\n")
                stdin.flush()
            except Exception as exc:  # pragma: no cover - best effort logging
                logger.exception("Failed to send command to server")
                return {
                    "success": False,
                    "message": f"Failed to send command: {exc}"
                }

        return {"success": True, "message": "Command sent"}

    def _get_psutil_process(self):
        if not psutil or not self.is_running or not self._process:
            self._ps_process = None
            return None

        if self._ps_process and self._ps_process.pid == self._process.pid:
            return self._ps_process

        try:
            ps = psutil.Process(self._process.pid)
            ps.cpu_percent(interval=None)  # Prime the baseline; first call always returns 0.0
            self._ps_process = ps
        except (psutil.Error, ProcessLookupError):  # pragma: no cover - psutil errors
            self._ps_process = None
        return self._ps_process

    def _get_ram_usage_bytes(self) -> Optional[int]:
        process = self._get_psutil_process()
        if not process:
            return None
        try:
            return process.memory_info().rss
        except (psutil.Error, ProcessLookupError):
            self._ps_process = None
            return None

    def _get_cpu_percent(self) -> Optional[float]:
        process = self._get_psutil_process()
        if not process:
            return None
        try:
            # Raw psutil CPU% — can exceed 100 on multi-core hosts (e.g. 400 on
            # 4 cores). We report it unnormalized and ship the core count
            # (see status()) so the UI can show either the per-core average
            # (Task-Manager style) or the raw total, per user preference.
            return round(process.cpu_percent(interval=None), 1)
        except (psutil.Error, ProcessLookupError):
            self._ps_process = None
            return None
