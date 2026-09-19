@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo.
echo ============================================================
echo   MORROWGLASS AUTOVIDEO - FIRST-TIME WINDOWS SETUP
echo ============================================================
echo.

set "UV_CMD="

where uv >nul 2>nul
if not errorlevel 1 (
    set "UV_CMD=uv"
    goto :uv_ready
)

echo [1/5] uv was not found. Installing it with Python...

where py >nul 2>nul
if not errorlevel 1 (
    py -3 -m pip install --user --upgrade uv
    if errorlevel 1 goto :uv_install_failed
    set "UV_CMD=py -3 -m uv"
    goto :uv_ready
)

where python >nul 2>nul
if not errorlevel 1 (
    python -m pip install --user --upgrade uv
    if errorlevel 1 goto :uv_install_failed
    set "UV_CMD=python -m uv"
    goto :uv_ready
)

echo.
echo [ERROR] Python was not found.
echo Install Python 3.11 or newer, then run this file again.
echo.
pause
exit /b 1

:uv_install_failed
echo.
echo [ERROR] Failed to install uv.
echo Check your internet connection and Python installation.
echo.
pause
exit /b 1

:uv_ready
echo [2/5] Preparing Python 3.11...
%UV_CMD% python install 3.11
if errorlevel 1 (
    echo.
    echo [ERROR] Could not prepare Python 3.11.
    echo.
    pause
    exit /b 1
)

echo [3/5] Installing project dependencies...
%UV_CMD% sync --frozen --python 3.11
if errorlevel 1 (
    echo.
    echo [ERROR] Dependency installation failed.
    echo.
    pause
    exit /b 1
)

echo [4/5] Creating/verifying config.toml...
%UV_CMD% run --python 3.11 python -c "from app.config import config; print('Config:', config.config_file)"
if errorlevel 1 (
    echo.
    echo [ERROR] Could not initialize the configuration.
    echo.
    pause
    exit /b 1
)

echo [5/5] Checking Morrowglass services...
echo.
%UV_CMD% run --python 3.11 python morrowglass.py doctor

echo.
echo ============================================================
echo   SETUP FINISHED
echo ============================================================
echo.
echo If Doctor reports Kokoro or ComfyUI as unavailable, that does
echo not mean Python setup failed. Those local AI services are
echo configured/tested separately.
echo.
echo Next launch:
echo   Double-click morrowglass_webui.bat
echo.
pause
exit /b 0
