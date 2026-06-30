"""Minecraft server management service."""
import logging
import os
import re
import subprocess
import threading
import time
from typing import Iterable, List, Optional

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
    _PLAYER_JOIN_RE = re.compile(r'\[.*?INFO\]: (.+) joined the game')
    _PLAYER_LEAVE_RE = re.compile(r'\[.*?INFO\]: (.+) left the game')

    def __init__(self, cwd: str, command: Optional[Iterable[str]] = None):
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
        # viewer's local timezone. Storing the pair as one tuple keeps the
        # lock-free append in ``_stream`` a single atomic list op.
        self._stdout_buffer: List[tuple[str, str]] = []
        self._stderr_buffer: List[tuple[str, str]] = []
        self._players: Dict[str, OnlinePlayer] = {}
        self._lock = threading.Lock()

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

        def _stream(pipe, buffer: List[tuple[str, str]]):
            for line in iter(pipe.readline, ""):
                buffer.append((iso_z_now(), line))
                if len(buffer) > self.MAX_LOG_LINES:
                    del buffer[: len(buffer) - self.MAX_LOG_LINES]
                join_match = self._PLAYER_JOIN_RE.search(line)
                if join_match:
                    name = join_match.group(1)
                    with self._lock:
                        self._players[name] = OnlinePlayer(
                            name=name,
                            joined_at=datetime.now(timezone.utc),
                        )
                else:
                    leave_match = self._PLAYER_LEAVE_RE.search(line)
                    if leave_match:
                        with self._lock:
                            self._players.pop(leave_match.group(1), None)
                print(line, end="")
            pipe.close()

        self._stdout_buffer = []
        self._stderr_buffer = []
        self._stdout_thread = threading.Thread(
            target=_stream, args=(self._process.stdout, self._stdout_buffer), daemon=True
        )
        self._stderr_thread = threading.Thread(
            target=_stream, args=(self._process.stderr, self._stderr_buffer), daemon=True
        )
        self._stdout_thread.start()
        self._stderr_thread.start()

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
            self._process = None
            self._ps_process = None
            self._players.clear()
            self._stdout_thread = None
            self._stderr_thread = None

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
        if self._process and running:
            status["pid"] = self._process.pid
        with self._lock:
            if not running:
                self._players.clear()
            status["players"] = {"online": len(self._players)}
        return status

    def tail_logs(self, limit: int = 200) -> dict:
        with self._lock:
            stdout = self._stdout_buffer[-limit:]
            stderr = self._stderr_buffer[-limit:]
            running = self.is_running
        return {
            "stdout": [{"ts": ts, "text": text} for ts, text in stdout],
            "stderr": [{"ts": ts, "text": text} for ts, text in stderr],
            "running": running
        }

    def wait_for_log(
        self,
        pattern: "re.Pattern[str] | str",
        timeout: float = 60.0,
        poll_interval: float = 0.1,
    ) -> bool:
        """Wait for a log line matching ``pattern`` to appear after now.

        Snapshots ``len(self._stdout_buffer)`` under the lock, then polls
        every ``poll_interval`` seconds for any newly-appended stdout line
        that matches. Lines already in the buffer at call time are ignored
        — callers want confirmation of an action they just triggered (e.g.
        ``save-all flush``), not the historical state.

        Returns True on match, False on timeout. Uses ``time.monotonic``
        so a wall-clock jump (NTP adjust, suspend/resume) doesn't extend
        or truncate the wait.
        """
        if isinstance(pattern, str):
            pattern = re.compile(pattern)

        with self._lock:
            start_index = len(self._stdout_buffer)

        deadline = time.monotonic() + max(0.0, timeout)
        while time.monotonic() < deadline:
            with self._lock:
                # Snapshot the slice under the lock so the streaming
                # thread can't truncate-then-resize the buffer mid-iter.
                pending = self._stdout_buffer[start_index:]
                start_index = len(self._stdout_buffer)
            for _, line in pending:
                if pattern.search(line):
                    return True
            time.sleep(poll_interval)

        # One final sweep — covers the race where the matching line
        # arrives after the last poll-sleep but before timeout.
        with self._lock:
            pending = self._stdout_buffer[start_index:]
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
            return round(process.cpu_percent(interval=None), 1)
        except (psutil.Error, ProcessLookupError):
            self._ps_process = None
            return None
