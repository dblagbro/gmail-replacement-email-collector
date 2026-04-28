"""Desktop-mode entry point (Windows .exe / standalone).

Differs from Docker mode by:
  - Binding to 127.0.0.1 (not 0.0.0.0)
  - Auto-opening the browser to the UI on first run
  - Showing a system tray icon
"""
from __future__ import annotations
import logging
import sys
import time
import webbrowser

import uvicorn

from app import tray
from app.config import PORT


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    url = f"http://127.0.0.1:{PORT}/"
    print(f"Starting Email Collector on {url}")
    print("(close the tray icon to exit)")

    tray.start_tray_in_background(url)

    # Open browser shortly after server boots
    def _open():
        time.sleep(2.0)
        webbrowser.open(url)

    import threading
    threading.Thread(target=_open, daemon=True).start()

    config = uvicorn.Config(
        "app.main:app",
        host="127.0.0.1",
        port=PORT,
        log_level="info",
        access_log=False,
    )
    server = uvicorn.Server(config)
    server.run()


if __name__ == "__main__":
    main()
