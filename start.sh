#!/bin/bash
# OpenFloat Data Formatter - Start Script
# Usage: ./start.sh [api|ui|both]
#
# Requires uv (https://docs.astral.sh/uv/). `uv sync` creates .venv on first
# run and installs the project editable, so imports just work — no venv
# activation or PYTHONPATH needed.
#
# Both servers bind to 127.0.0.1. Uploads and reports here carry names, phone
# numbers and staff IDs, and the API has no authentication — on shared Wi-Fi
# the default (all interfaces) puts that on the network. Pass an explicit
# --host/--server.address if you genuinely need to reach it from elsewhere.

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

uv sync --python 3.12

MODE="${1:-ui}"

case "$MODE" in
    api)
        echo "Starting FastAPI server on http://localhost:8000"
        echo "API docs: http://localhost:8000/docs"
        uv run uvicorn openfloat_formatter.main:app --reload --host 127.0.0.1 --port 8000
        ;;
    ui)
        echo "Starting Streamlit UI on http://localhost:8501"
        uv run streamlit run src/openfloat_formatter/ui/app.py --server.port 8501 --server.address=127.0.0.1
        ;;
    both)
        echo "Starting both FastAPI (port 8000) and Streamlit (port 8501)"
        echo "API docs: http://localhost:8000/docs"
        echo "UI: http://localhost:8501"
        uv run uvicorn openfloat_formatter.main:app --host 127.0.0.1 --port 8000 &
        API_PID=$!
        uv run streamlit run src/openfloat_formatter/ui/app.py --server.port 8501 --server.address=127.0.0.1 &
        UI_PID=$!
        echo ""
        echo "PIDs: API=$API_PID, UI=$UI_PID"
        echo "Press Ctrl+C to stop both servers."
        trap "kill $API_PID $UI_PID 2>/dev/null; exit" INT TERM
        wait
        ;;
    *)
        echo "Usage: ./start.sh [api|ui|both]"
        echo ""
        echo "  api   - Start FastAPI server only (http://localhost:8000)"
        echo "  ui    - Start Streamlit UI only (http://localhost:8501)"
        echo "  both  - Start both servers"
        echo ""
        echo "Default: ui"
        exit 1
        ;;
esac