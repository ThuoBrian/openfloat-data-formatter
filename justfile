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

# The leading `-` on ui/api ignores the exit code: closing the terminal or
# Ctrl+C kills the server, which just would otherwise report as "recipe failed".

# Streamlit UI on http://localhost:8501
ui:
    -uv run streamlit run src/openfloat_formatter/ui/app.py --server.port 8501 --server.address=127.0.0.1

# Desktop + Start menu shortcut (with the app icon) that launches run.bat here
shortcut:
    powershell -NoProfile -ExecutionPolicy Bypass -File install/create-shortcut.ps1

# FastAPI server on http://localhost:8000 (docs at /docs)
api:
    -uv run uvicorn openfloat_formatter.main:app --reload --host 127.0.0.1 --port 8000

# The local app launcher on http://127.0.0.1:8765 (what run.bat will start once
# the React page replaces Streamlit)
app:
    -uv run openfloat

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

# Regenerate docs/openapi.json after an API change (a test fails until you do),
# then the front end's TypeScript types from it
openapi:
    uv run python scripts/export_openapi.py
    npm --prefix frontend run gen:api

# React page in development on http://127.0.0.1:5173, forwarding API calls to
# `just api` (run that too, or use `just web-both`)
web-dev:
    -npm --prefix frontend run dev

# API and the React dev page together; Ctrl+C stops both
[parallel]
web-both: api web-dev

# Front-end checks: type-check, tests, production build
web-check:
    npm --prefix frontend run typecheck
    npm --prefix frontend test
    npm --prefix frontend run build

# Regenerate docs/processmaker-input-template.xlsx
template:
    uv run python scripts/generate_processmaker_template.py
