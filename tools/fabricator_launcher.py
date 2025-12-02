"""Windows system tray launcher for Fabricator.

Build example (PyInstaller):
    pyinstaller --onefile --noconsole --icon=fabricator_icon.ico tools/fabricator_launcher.py
"""
from __future__ import annotations

import atexit
import subprocess
import sys
import time
import webbrowser
from pathlib import Path
from typing import Optional

import pystray
from PIL import Image, ImageDraw

BACKEND_URL = "http://127.0.0.1:8000"
BACKEND_MODULE = "fabricator_backend"
BACKEND_PROCESS: Optional[subprocess.Popen] = None


def _resource_path() -> Path:
    """Resolve the directory containing bundled resources."""

    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))


def _project_root() -> Path:
    """Get the project root in source or bundled layouts."""

    base = _resource_path()
    return base.parent if base.name == "tools" else base


def _backend_workdir() -> Path:
    """Directory from which the backend module should be started."""

    return _project_root() / "backend"


def _find_icon() -> Optional[Path]:
    """Look for an icon bundled alongside the launcher."""

    base = _resource_path()
    for name in ("fabricator_icon.png", "fabricator_icon.ico"):
        candidate = base / name
        if candidate.exists():
            return candidate
    return None


def _load_icon_image() -> Image.Image:
    """Load the tray icon image, falling back to a simple placeholder."""

    icon_path = _find_icon()
    if icon_path:
        return Image.open(icon_path)

    image = Image.new("RGBA", (64, 64), (50, 50, 50, 255))
    draw = ImageDraw.Draw(image)
    draw.rectangle((8, 8, 56, 56), outline=(200, 200, 200, 255), width=4)
    draw.line((8, 8, 56, 56), fill=(120, 180, 255, 255), width=4)
    draw.line((8, 56, 56, 8), fill=(120, 180, 255, 255), width=4)
    return image


def _python_command() -> str:
    """Locate the Python executable used to run the backend."""

    if getattr(sys, 'frozen', False):
        bundled_python = Path(sys.executable).with_name('python.exe')
        if bundled_python.exists():
            return str(bundled_python)
    return sys.executable


def start_backend() -> None:
    """Start the Flask backend as a subprocess."""

    global BACKEND_PROCESS
    if BACKEND_PROCESS and BACKEND_PROCESS.poll() is None:
        return

    command = [_python_command(), "-m", BACKEND_MODULE]
    BACKEND_PROCESS = subprocess.Popen(
        command,
        cwd=str(_backend_workdir()),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def stop_backend() -> None:
    """Terminate the backend subprocess cleanly."""

    global BACKEND_PROCESS
    if not BACKEND_PROCESS:
        return

    if BACKEND_PROCESS.poll() is None:
        BACKEND_PROCESS.terminate()
        try:
            BACKEND_PROCESS.wait(timeout=5)
        except subprocess.TimeoutExpired:
            BACKEND_PROCESS.kill()
    BACKEND_PROCESS = None


@atexit.register
def _cleanup_process() -> None:
    stop_backend()


def open_ui() -> None:
    """Open the Fabricator UI in the default browser."""

    webbrowser.open(BACKEND_URL)


def _on_open(icon: pystray.Icon, item: pystray.MenuItem) -> None:  # type: ignore[unused-argument]
    open_ui()


def _on_quit(icon: pystray.Icon, item: pystray.MenuItem) -> None:  # type: ignore[unused-argument]
    icon.stop()
    stop_backend()


def _menu() -> pystray.Menu:
    return pystray.Menu(
        pystray.MenuItem("Open Fabricator", _on_open),
        pystray.MenuItem("Quit", _on_quit),
    )


def main() -> None:
    """Start the backend, open the UI, and show the tray icon."""

    start_backend()
    time.sleep(1)
    open_ui()

    tray_icon = pystray.Icon("Fabricator", _load_icon_image(), "Fabricator", menu=_menu())
    tray_icon.run()


if __name__ == "__main__":
    main()
