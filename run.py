"""Entry point for the Fabricator application with system tray support."""
import logging
import os
import sys
import threading
import time
import webbrowser

logger = logging.getLogger(__name__)


# ============================================
# Path Configuration for PyInstaller
# ============================================

def get_base_path() -> str:
    """Return base path that works for both dev mode and bundled exe."""
    if getattr(sys, 'frozen', False):
        return sys._MEIPASS  # type: ignore[attr-defined]
    return os.path.dirname(os.path.abspath(__file__))


def setup_paths() -> None:
    """Ensure cwd is a stable, writable location for the bundled exe.

    On Windows the .exe is often launched from Downloads or another transient
    folder, so we cd into %APPDATA%\\Fabricator. On POSIX bundled runs we cd
    into ~/.fabricator (the same path appdata_dir() now returns for POSIX).
    """
    if not getattr(sys, 'frozen', False):
        return
    from backend.utils.platform import appdata_dir
    os.chdir(appdata_dir())


# ============================================
# System Tray Icon
# ============================================

def _has_tray_support() -> bool:
    """Return True when the environment can show a tray icon."""
    if os.environ.get('FABRICATOR_NO_TRAY') == '1':
        return False
    if sys.platform.startswith('win') or sys.platform == 'darwin':
        return True
    return bool(os.environ.get('DISPLAY'))


def create_tray_icon(port: int, on_quit_callback):
    """Create system tray icon plus menu actions."""
    import pystray
    from PIL import Image, ImageDraw

    def create_icon_image():
        base_path = get_base_path()
        icon_path = os.path.join(base_path, 'assets', 'icon.ico')
        if os.path.exists(icon_path):
            return Image.open(icon_path)

        # Simple fallback icon (green square with "F")
        size = 64
        image = Image.new('RGB', (size, size), color='#2E7D32')
        draw = ImageDraw.Draw(image)
        draw.text((20, 12), 'F', fill='white')
        return image

    def on_open_browser(icon, item):  # pylint: disable=unused-argument
        webbrowser.open(f"http://127.0.0.1:{port}")

    def on_open_data_folder(icon, item):  # pylint: disable=unused-argument
        from backend.utils.platform import appdata_dir
        try:
            os.startfile(str(appdata_dir()))  # type: ignore[attr-defined]
        except OSError as exc:
            print(f"Could not open data folder: {exc}")

    def on_quit(icon, item):  # pylint: disable=unused-argument
        icon.stop()
        on_quit_callback()

    # "Open Data Folder" is Windows-only because the action uses os.startfile
    # (Windows-only). On POSIX appdata_dir() does return a real path now, but
    # opening it portably would need xdg-open / `open` and is out of scope.
    from backend.utils.platform import is_windows
    menu_items = [pystray.MenuItem('🌐 Open in Browser', on_open_browser, default=True)]
    if is_windows():
        menu_items.append(pystray.MenuItem('📂 Open Data Folder', on_open_data_folder))
    menu_items.append(pystray.Menu.SEPARATOR)
    menu_items.append(pystray.MenuItem('❌ Quit', on_quit))
    menu = pystray.Menu(*menu_items)

    return pystray.Icon(
        name='Fabricator',
        icon=create_icon_image(),
        title='Fabricator Server',
        menu=menu,
    )


# ============================================
# Browser Auto-Open
# ============================================

def open_browser_delayed(host: str, port: int, delay: float = 1.5) -> None:
    """Open the browser after a short delay so the server is ready."""

    def _open() -> None:
        time.sleep(delay)
        url = f"http://{'127.0.0.1' if host == '0.0.0.0' else host}:{port}"
        webbrowser.open(url)

    threading.Thread(target=_open, daemon=True).start()


# ============================================
# System Config
# ============================================

_SYSTEM_ENV_FILE = "/etc/fabricator/fabricator.env"


def _load_system_env() -> None:
    """Load ``/etc/fabricator/fabricator.env`` without overriding existing env vars.

    The systemd service unit already injects these variables via
    ``EnvironmentFile=``, so ``override=False`` means production runs are
    unaffected while local dev runs (no systemd) still pick up the file when
    it happens to exist.  Missing file → silent no-op.
    """
    if not os.path.exists(_SYSTEM_ENV_FILE):
        return
    try:
        from dotenv import load_dotenv
        load_dotenv(_SYSTEM_ENV_FILE, override=False)
    except Exception as exc:  # pragma: no cover
        print(f"[WARN] Could not load {_SYSTEM_ENV_FILE}: {exc}")


# ============================================
# Main Entry Point
# ============================================

def main() -> None:
    setup_paths()
    _load_system_env()

    from backend.core import create_app, get_config

    app = create_app()
    config = get_config()

    # Auto-start the playit tunnel if enabled. agent.is_enabled() honours the
    # persisted desired-state file first (so a tunnel toggled on from the
    # dashboard survives a restart), falling back to the PLAYIT_ENABLED env
    # var for fresh / env-driven installs. Isolated in try/except so a missing
    # binary or runtime-dir permission error can't take down Flask.
    try:
        from backend.playit import agent as playit_agent
        if playit_agent.is_enabled():
            playit_agent.start()
    except Exception as exc:
        logger.warning("playit auto-start failed: %s", exc)

    def shutdown() -> None:
        os._exit(0)  # noqa: SCS2 - we want an immediate exit

    def run_server() -> None:
        from werkzeug.serving import make_server

        server = make_server(config.HOST, config.PORT, app, threaded=True)
        server.serve_forever()

    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()

    open_browser_delayed(config.HOST, config.PORT)

    if _has_tray_support():
        try:
            tray_icon = create_tray_icon(config.PORT, shutdown)
            tray_icon.run()
            return
        except Exception as exc:  # pragma: no cover - best effort logging
            print(f"Tray icon unavailable ({exc}); running headless.")

    print('Fabricator server running without tray icon. Press Ctrl+C to stop.')
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        shutdown()


if __name__ == '__main__':
    main()
