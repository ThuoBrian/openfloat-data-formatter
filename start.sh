#!/bin/bash
# OpenFloat Data Formatter - Start Script
# Usage: ./start.sh [api|ui|both]

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Create venv if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate venv and install dependencies
source venv/bin/activate
pip install -q -r requirements.txt

export PYTHONPATH=src

MODE="${1:-ui}"

case "$MODE" in
    api)
        echo "Starting FastAPI server on http://localhost:8000"
        echo "API docs: http://localhost:8000/docs"
        uvicorn src.backend.main:app --reload --host 0.0.0.0 --port 8000
        ;;
    ui)
        echo "Starting Streamlit UI on http://localhost:8501"
        streamlit run src/frontend/app.py --server.port 8501
        ;;
    both)
        echo "Starting both FastAPI (port 8000) and Streamlit (port 8501)"
        echo "API docs: http://localhost:8000/docs"
        echo "UI: http://localhost:8501"
        uvicorn src.backend.main:app --host 0.0.0.0 --port 8000 &
        API_PID=$!
        streamlit run src/frontend/app.py --server.port 8501 &
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