@echo off
setlocal enabledelayedexpansion
title OpenFloat Data Formatter

echo OpenFloat Data Formatter
echo ====================

:: ── 1. Install uv if not already present ─────────────────────────────────────
where uv >nul 2>&1
if %errorlevel% neq 0 (
    echo Installing uv ^(one-time^)...
    powershell -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
    if !errorlevel! neq 0 (
        echo.
        echo ERROR: Could not install uv. Check your internet connection and try again.
        pause
        exit /b 1
    )
    :: Reload PATH so uv is available in this session
    for /f "tokens=*" %%i in ('powershell -Command "[System.Environment]::GetEnvironmentVariable(\"PATH\",\"User\")"') do set "PATH=%%i;%PATH%"
)

:: ── 2. Set up the Python environment ──────────────────────────────────────────
:: Strip trailing backslash from %~dp0 before passing to --project
set "APPDIR=%~dp0"
if "%APPDIR:~-1%"=="\" set "APPDIR=%APPDIR:~0,-1%"

:: uv sync is idempotent: it creates .venv on first run and self-heals on every
:: update (the installer wipes the folder), so run it unconditionally.
:: --no-dev: end users don't need pytest/httpx.
echo Setting up Python environment ^(this may take a few minutes on first run^)...
uv sync --no-dev --python 3.12 --project "%APPDIR%"
if !errorlevel! neq 0 (
    echo.
    echo ERROR: Could not set up Python environment.
    pause
    exit /b 1
)

:: ── 3. Launch the app ─────────────────────────────────────────────────────────
echo.
echo Starting app. A browser tab will open shortly.
echo To stop it, click "Close the app" on the page, or close this window.
echo.
:: The launcher serves the page and its API on 127.0.0.1 only, opens the
:: browser, and exits with code 0 when the page's "Close the app" is used.
"%APPDIR%\.venv\Scripts\openfloat.exe"

if errorlevel 1 (
    echo.
    echo App exited with an error. See above for details.
    pause
)

endlocal