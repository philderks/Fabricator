import os
import subprocess
import threading
from typing import List, Optional


class ServerService:
    """Manage the lifecycle of an external server process."""

    def __init__(self, command: Optional[List[str]] = None, cwd: Optional[str] = None):
        env_command = os.environ.get("SERVER_COMMAND")
        parsed_env_command: Optional[List[str]] = None
        if env_command:
            parsed_env_command = env_command.split()

        self.command = command or parsed_env_command
        self.cwd = cwd
        self._process: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()

    def start(self) -> dict:
        """Start the server process if it is not already running."""
        with self._lock:
            if self.is_running:
                return {"status": "running", "message": "Server is already running"}

            command_to_run = self.command.split() if isinstance(self.command, str) else self.command

            if not command_to_run:
                return {
                    "status": "stopped",
                    "message": "No server command configured. Set SERVER_COMMAND or pass a command list.",
                }

            try:
                self._process = subprocess.Popen(
                    command_to_run,
                    cwd=self.cwd,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    text=True,
                )
                return {"status": "running", "message": "Server started", "command": self.command}
            except Exception as exc:
                self._process = None
                return {"status": "stopped", "message": f"Failed to start server: {exc}"}

    def stop(self) -> dict:
        """Stop the server process if it is running."""
        with self._lock:
            if not self.is_running or not self._process:
                return {"status": "stopped", "message": "Server is not running"}

            try:
                if self._process.stdin and not self._process.stdin.closed:
                    try:
                        self._process.stdin.write("stop\n")
                        self._process.stdin.flush()
                    except Exception:
                        pass

                self._process.terminate()
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
            finally:
                self._process = None

            return {"status": "stopped", "message": "Server stopped"}

    @property
    def is_running(self) -> bool:
        return bool(self._process and self._process.poll() is None)

    def status(self) -> dict:
        status_value = "running" if self.is_running else "stopped"
        message = "Server process is running" if self.is_running else "Server process is not running"
        return {"status": status_value, "message": message}
