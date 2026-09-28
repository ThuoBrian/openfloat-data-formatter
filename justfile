# Developer commands for the OpenFloat Data Formatter. Run `just` to list them.
#
# Staff don't use this — they double-click run.bat (see GUIDE.md).
#
# Both servers bind to 127.0.0.1. Uploads and reports here carry names, phone
# numbers and staff IDs, and the API has no authentication — Streamlit and
# uvicorn bind all interfaces by default, which on shared Wi-Fi puts that on
# the network. The --server.address/--host flags are load-bearing.

set windows-shell := ["powershell.exe", "-NoLogo", "-NoProfile", "-Command"]

[private]
default:
    @just --list

# Set up / refresh .venv (package installed editable, plus dev tools)
sync:
    uv sync --python 3.12

# Streamlit UI on http://localhost:8501
ui:
    uv run streamlit run src/openfloat_formatter/ui/app.py --server.port 8501 --server.address=127.0.0.1

# FastAPI server on http://localhost:8000 (docs at /docs)
api:
    uv run uvicorn openfloat_formatter.main:app --reload --host 127.0.0.1 --port 8000

# API and UI together in this terminal; Ctrl+C stops both
[parallel]
both: api ui

# Run pytest; extra arguments pass through (just test -k test_phone)
test *args:
    uv run pytest -v {{args}}

# Lint with ruff
lint:
    uv run ruff check .

# Type-check with mypy
typecheck:
    uv run mypy

# Everything CI checks: lint, type-check, tests
check: lint typecheck test

# Regenerate docs/processmaker-input-template.xlsx
template:
    uv run python scripts/generate_processmaker_template.py
