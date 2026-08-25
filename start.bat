@echo off
REM OpenFloat Data Formatter - Start Script
REM Usage: start.bat [api|ui|both]

cd /d "%~dp0"

REM Create venv if it doesn't exist
if not exist "venv" (
    echo Creating virtual environment...
    python -m venv venv
)

REM Activate venv and install dependencies
call venv\Scripts\activate.bat
pip install -q -r requirements.txt

set PYTHONPATH=src

if "%1"=="" set "MODE=ui"
if not "%1"=="" set "MODE=%1"

if /i "%MODE%"=="api" (
    echo Starting FastAPI server on http://localhost:8000
    echo API docs: http://localhost:8000/docs
    uvicorn src.backend.main:app --reload --host 0.0.0.0 --port 8000
    goto :eof
)

if /i "%MODE%"=="ui" (
    echo Starting Streamlit UI on http://localhost:8501
    streamlit run src/frontend/app.py --server.port 8501
    goto :eof
)

if /i "%MODE%"=="both" (
    echo Starting both FastAPI (port 8000) and Streamlit (port 8501)
    echo API docs: http://localhost:8000/docs
    echo UI: http://localhost:8501
    start "FastAPI" uvicorn src.backend.main:app --host 0.0.0.0 --port 8000
    start "Streamlit" streamlit run src/frontend/app.py --server.port 8501
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