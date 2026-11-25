"""Run the app on this computer: the HTTP API, bound to 127.0.0.1 only.

This is what `run.bat` will launch once the React page replaces Streamlit
(see AGENTS.md). It exists, rather than a bare `uvicorn` command, so that
"Close the app" can stop the server with exit code 0. `main._shut_down`
calls the hook registered here, and uvicorn then returns normally instead of
re-raising a signal and exiting non-zero.

Usage:
    uv run openfloat
"""

from __future__ import annotations

import uvicorn

# 127.0.0.1, never 0.0.0.0: the API has no login, and uploads carry names,
# phone numbers and staff IDs.
HOST = "127.0.0.1"
# Clear of Streamlit (8501) and `just api` (8000), so all three can run at once
# during the side-by-side period.
PORT = 8765


def main() -> None:
    # Imported here so a bad .env fails inside main(), not at import time.
    from .main import app

    server = uvicorn.Server(uvicorn.Config(app, host=HOST, port=PORT))

    def request_shutdown() -> None:
        server.should_exit = True

    app.state.shutdown = request_shutdown
    server.run()
    if not server.started:  # e.g. the port is already taken
        raise SystemExit(1)


if __name__ == "__main__":
    main()
