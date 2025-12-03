"""Entry point for the Fabricator application."""
"""Entry point for the Fabricator application."""
import threading
import time
import webbrowser

from backend.core import create_app, get_config

def open_browser_later(host: str, port: int) -> None:
    """Open the UI in the browser after a short delay."""
    def _target():
        time.sleep(1.5)
        url = f"http://{host}:{port}"
        webbrowser.open(url)
    t = threading.Thread(target=_target, daemon=True)
    t.start()

if __name__ == '__main__':
    app = create_app()
    config = get_config()

    open_browser_later(config.HOST, config.PORT)
    
    app.run(
        debug=config.DEBUG,
        host=config.HOST,
        port=config.PORT
    )
