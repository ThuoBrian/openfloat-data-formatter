#!/bin/bash
# OpenFloat Data Formatter - Start Script
# Usage: ./start.sh [api|ui|both]
#
# Requires uv (https://docs.astral.sh/uv/). `uv sync` creates .venv on first
# run and installs the project editable, so imports just work — no venv
# activation or PYTHONPATH needed.

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

uv sync --python 3.12

MODE="${1:-ui}"

case "$MODE" in
    api)
        echo "Starting FastAPI server on http://localhost:8000"
        echo "API docs: http://localhost:8000/docs"
        uv run uvicorn openfloat_formatter.main:app --reload --host 0.0.0.0 --port 8000
        ;;
    ui)
        echo "Starting Streamlit UI on http://localhost:8501"
        uv run streamlit run src/openfloat_formatter/ui/app.py --server.port 8501
        ;;
    both)
        echo "Starting both FastAPI (port 8000) and Streamlit (port 8501)"
        echo "API docs: http://localhost:8000/docs"
        echo "UI: http://localhost:8501"
        uv run uvicorn openfloat_formatter.main:app --host 0.0.0.0 --port 8000 &
        API_PID=$!
        uv run streamlit run src/openfloat_formatter/ui/app.py --server.port 8501 &
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