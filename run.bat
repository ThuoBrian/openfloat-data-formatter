@echo off
setlocal
title OpenFloat Data Formatter

echo OpenFloat Data Formatter
echo ====================

:: ── 1. Install uv if not already present ─────────────────────────────────────
where uv >nul 2>&1
if %errorlevel% neq 0 (
    echo Installing uv ^(one-time^)...
    powershell -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
    if %errorlevel% neq 0 (
        echo.
        echo ERROR: Could not install uv. Check your internet connection and try again.
        pause
        exit /b 1
    )
    :: Reload PATH so uv is available in this session
    for /f "tokens=*" %%i in ('powershell -Command "[System.Environment]::GetEnvironmentVariable(\"PATH\",\"User\")"') do set "PATH=%%i;%PATH%"
)

:: ── 2. Create virtual environment and install dependencies ────────────────────
:: Strip trailing backslash from %~dp0 before passing to --project
set "APPDIR=%~dp0"
if "%APPDIR:~-1%"=="\" set "APPDIR=%APPDIR:~0,-1%"

if not exist "%APPDIR%\.venv" (
    echo Setting up Python environment ^(one-time, this may take a few minutes^)...
    uv sync --python 3.12 --project "%APPDIR%"
    if %errorlevel% neq 0 (
        echo.
        echo ERROR: Could not set up Python environment.
        pause
        exit /b 1
    )
)

:: ── 3. Launch the app ─────────────────────────────────────────────────────────
echo.
echo Starting app. A browser tab will open shortly.
echo Close this window to stop it.
echo.
"%APPDIR%\.venv\Scripts\streamlit.exe" run "%APPDIR%\src\frontend\app.py" --server.address=127.0.0.1

if errorlevel 1 (
    echo.
    echo App exited with an error. See above for details.
    pause
)

endlocal
