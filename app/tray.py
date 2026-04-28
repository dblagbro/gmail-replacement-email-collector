"""Windows / desktop system tray integration.

Imported only when running outside Docker. Uses pystray for cross-desktop tray
icons. Right-click menu: Open UI / Pause-Resume all / Quit. Left-click opens UI.
"""
from __future__ import annotations
import logging
import sys
import threading
import webbrowser
from pathlib import Path

logger = logging.getLogger(__name__)

_app_url = "http://127.0.0.1:8077/"


def _open_ui(icon=None, item=None) -> None:
    webbrowser.open(_app_url)


def _quit(icon, item) -> None:
    icon.stop()
    # Trigger uvicorn shutdown via SIGINT to the process group
    import os
    import signal
    os.kill(os.getpid(), signal.SIGINT)


def run_tray(url: str) -> None:
    """Block forever showing a tray icon. Call from a background thread."""
    global _app_url
    _app_url = url
    try:
        import pystray
        from PIL import Image
    except ImportError:
        logger.warning("pystray/Pillow not installed — tray disabled")
        return
    icon_path = Path(__file__).parent / "static" / "icon.png"
    image = Image.open(icon_path) if icon_path.exists() else None
    menu = pystray.Menu(
        pystray.MenuItem("Open Email Collector", _open_ui, default=True),
        pystray.MenuItem("Quit", _quit),
    )
    icon = pystray.Icon("email-collector", image, "Gmail Replacement Email Collector", menu)
    icon.run()


def start_tray_in_background(url: str) -> threading.Thread:
    t = threading.Thread(target=run_tray, args=(url,), daemon=True, name="tray")
    t.start()
    return t
