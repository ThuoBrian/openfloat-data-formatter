@echo off
REM OpenFloat Data Formatter - Start Script
REM Usage: start.bat [api|ui|both]
REM
REM Requires uv (https://docs.astral.sh/uv/). `uv sync` creates .venv on first
REM run and installs the project editable, so imports just work — no venv
REM activation or PYTHONPATH needed.
REM
REM Both servers bind to 127.0.0.1. Uploads and reports here carry names, phone
REM numbers and staff IDs, and the API has no authentication — on shared Wi-Fi
REM the default (all interfaces) puts that on the network. Pass an explicit
REM --host/--server.address if you genuinely need to reach it from elsewhere.

cd /d "%~dp0"

uv sync --python 3.12
if errorlevel 1 (
    echo ERROR: Could not set up the Python environment.
    exit /b 1
)

if "%1"=="" set "MODE=ui"
if not "%1"=="" set "MODE=%1"

if /i "%MODE%"=="api" (
    echo Starting FastAPI server on http://localhost:8000
    echo API docs: http://localhost:8000/docs
    uv run uvicorn openfloat_formatter.main:app --reload --host 127.0.0.1 --port 8000
    goto :eof
)

if /i "%MODE%"=="ui" (
    echo Starting Streamlit UI on http://localhost:8501
    uv run streamlit run src/openfloat_formatter/ui/app.py --server.port 8501 --server.address=127.0.0.1
    goto :eof
)

if /i "%MODE%"=="both" (
    echo Starting both FastAPI (port 8000) and Streamlit (port 8501)
    echo API docs: http://localhost:8000/docs
    start "FastAPI" uv run uvicorn openfloat_formatter.main:app --host 127.0.0.1 --port 8000
    start "Streamlit" uv run streamlit run src/openfloat_formatter/ui/app.py --server.port 8501 --server.address=127.0.0.1
    echo.
    echo Both servers started in separate windows. Close them to stop.
    goto :eof
)

echo Usage: start.bat [api^|ui^|both]
echo.
echo   api   - Start FastAPI server only (http://localhost:8000)
echo   ui    - Start Streamlit UI only (http://localhost:8501)
echo   both  - Start both servers
echo.
echo Default: ui