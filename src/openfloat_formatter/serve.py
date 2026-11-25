"""Run the app on this computer: the page and its API, on 127.0.0.1 only.

This is what `run.bat` launches. It exists, rather than a bare `uvicorn`
command, for four things:

- "Close the app" stops the server with exit code 0. `main._shut_down`
  calls the hook registered here, and uvicorn returns normally instead of
  re-raising a signal and exiting non-zero.
- The browser opens on the page once the server is actually listening.
- Starting it twice (a double double-click) opens the copy that is already
  running instead of failing on a busy port.
- Ctrl+C in the console window also exits 0. uvicorn stops cleanly on it but
  then re-raises it as KeyboardInterrupt, which would leave run.bat paused on
  "App exited with an error".

Usage:
    uv run openfloat
"""

from __future__ import annotations

import sys
import threading
import time
import urllib.request
import webbrowser

import uvicorn
from pydantic import ValidationError

# 127.0.0.1, never 0.0.0.0: the API has no login, and uploads carry names,
# phone numbers and staff IDs.
HOST = "127.0.0.1"
# Clear of `just api` (8000) and the Vite dev page (5173), so all can run at once.
PORT = 8765
URL = f"http://{HOST}:{PORT}/"

# How long to wait for the server to start listening before opening the page.
_STARTUP_TIMEOUT_SECONDS = 30.0


def already_running() -> bool:
    """Whether this app is already answering on PORT."""
    try:
        with urllib.request.urlopen(URL + "health", timeout=1) as response:
            return bool(response.status == 200)
    except OSError:
        return False


def _open_when_ready(server: uvicorn.Server) -> None:
    deadline = time.monotonic() + _STARTUP_TIMEOUT_SECONDS
    while not server.started:
        if server.should_exit or time.monotonic() > deadline:
            return
        time.sleep(0.1)
    webbrowser.open(URL)


def main() -> None:
    if already_running():
        print(f"OpenFloat Data Formatter is already running. Opening {URL}")
        webbrowser.open(URL)
        return

    # Imported here, not at the top: main.py reads .env when imported, and a
    # bad value there should get a sentence, not a traceback.
    try:
        from .main import app
    except ValidationError as exc:
        print(
            "\nThe app's settings file (.env in the app folder) has a value it can't use.\n"
            "Fix or delete that line, then start the app again.\n\n"
            f"Technical details: {exc}",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc

    server = uvicorn.Server(uvicorn.Config(app, host=HOST, port=PORT))

    def request_shutdown() -> None:
        server.should_exit = True

    app.state.shutdown = request_shutdown
    threading.Thread(target=_open_when_ready, args=(server,), daemon=True).start()
    print(f"OpenFloat Data Formatter is running at {URL}", flush=True)
    try:
        server.run()
    except KeyboardInterrupt:
        return  # Ctrl+C: uvicorn has already shut down cleanly
    if not server.started:  # e.g. something else holds the port
        print(f"Could not start on {URL}: is another program using port {PORT}?", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
