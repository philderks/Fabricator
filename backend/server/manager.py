"""Minecraft server management service."""
import os
import re
import shlex
import subprocess
import threading
import time
from typing import Iterable, List, Optional

try:
    import psutil  # type: ignore
except ImportError:  # pragma: no cover - optional dependency fallback
    psutil = None


class ServerManager:
    """Manages the lifecycle of a Minecraft server process."""

    DEFAULT_COMMAND = "java -Xmx2G -jar server.jar nogui"

    def __init__(self, command: Optional[Iterable[str]] = None, cwd: Optional[str] = None):
        env_command = os.environ.get("SERVER_COMMAND")
        parsed_env_command: Optional[List[str]] = None
        if env_command:
            parsed_env_command = self._split_command(env_command)

        self.command = self._parse_command(command or parsed_env_command) or self._split_command(
            self.DEFAULT_COMMAND
        )
        self.cwd = cwd or os.path.join(os.getcwd(), "server")
        self._memory_limit_bytes = self._extract_memory_limit_bytes(self.command)
        self._process: Optional[subprocess.Popen] = None
        self._ps_process: Optional["psutil.Process"] = None  # type: ignore[name-defined]
        self._stdout_thread: Optional[threading.Thread] = None
        self._stderr_thread: Optional[threading.Thread] = None
        self._stdout_buffer: List[str] = []
        self._stderr_buffer: List[str] = []
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
        posix_mode = os.name != "nt"
        return shlex.split(command, posix=posix_mode)

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

    def _check_java_version(self) -> tuple[bool, str]:
        result = subprocess.run([
            "java",
            "-version",
        ], capture_output=True, text=True)
        version_output = (result.stdout or "") + (result.stderr or "")
        if result.returncode != 0:
            return False, "Java executable not available"

        match = re.search(r'version "(\d+)', version_output)
        if not match:
            return False, "Could not determine Java version"

        major_version = int(match.group(1))
        if major_version < 21:
            return False, f"Java 21 is required (found Java {major_version})"

        return True, version_output.strip()

    def _start_log_streams(self) -> None:
        if not self._process:
            return

        def _stream(pipe, buffer: List[str]):
            for line in iter(pipe.readline, ""):
                buffer.append(line)
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
            )
            self._ps_process = None
            self._start_log_streams()
            time.sleep(0.5)

            if self._process.poll() is not None:
                exit_code = self._process.returncode
                stdout_tail = "".join(self._stdout_buffer[-10:])
                stderr_tail = "".join(self._stderr_buffer[-10:])
                self._process = None
                error_message = f"Server process exited immediately (code {exit_code})."
                if stdout_tail:
                    error_message += f" stdout: {stdout_tail.strip()}"
                if stderr_tail:
                    error_message += f" stderr: {stderr_tail.strip()}"
                return False, error_message

            return True, "Server started"
        except Exception as exc:
            self._process = None
            return False, f"Failed to start server: {exc}"

    def start(self) -> dict:
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
            java_ok, java_message = self._check_java_version()
            if not java_ok:
                return {"status": "stopped", "message": java_message}

            started, message = self._spawn_process(command_to_run)
            status = "running" if started else "stopped"
            combined_message = message
            if started:
                combined_message = f"{message} (Java verified: {java_message})"

            return {"status": status, "message": combined_message, "command": command_to_run}

    def stop(self) -> dict:
        """Stop the server process if it is running."""
        with self._lock:
            if not self.is_running or not self._process:
                return {"status": "stopped", "message": "Server is not running"}

            proc = self._process
            try:
                if self._process.stdin and not self._process.stdin.closed:
                    try:
                        self._process.stdin.write("stop\n")
                        self._process.stdin.flush()
                    except Exception:
                        pass

                proc.terminate()
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    pass
            finally:
                self._process = None
                self._ps_process = None

            return {"status": "stopped", "message": "Server stopped"}

    @property
    def is_running(self) -> bool:
        return bool(self._process and self._process.poll() is None)

    def status(self) -> dict:
        status_value = "running" if self.is_running else "stopped"
        message = "Server process is running" if self.is_running else "Server process is not running"
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
        if self._process and self.is_running:
            status["pid"] = self._process.pid
        return status

    def tail_logs(self, limit: int = 200) -> dict:
        with self._lock:
            stdout = self._stdout_buffer[-limit:]
            stderr = self._stderr_buffer[-limit:]
            running = self.is_running
        return {
            "stdout": stdout,
            "stderr": stderr,
            "running": running
        }

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
            self._ps_process = psutil.Process(self._process.pid)
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
