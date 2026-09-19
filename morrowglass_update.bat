@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo.
echo ============================================================
echo   MORROWGLASS AUTOVIDEO - UPDATE
echo ============================================================
echo.

where git >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Git was not found.
    pause
    exit /b 1
)

git status --porcelain
if not errorlevel 1 (
    for /f %%A in ('git status --porcelain ^| find /c /v ""') do set "CHANGE_COUNT=%%A"
)
if defined CHANGE_COUNT if not "%CHANGE_COUNT%"=="0" (
    echo.
    echo [ERROR] Local files have uncommitted changes.
    echo Update stopped to avoid overwriting them.
    echo.
    git status --short
    echo.
    pause
    exit /b 1
)

echo [1/3] Fetching latest Morrowglass development branch...
git fetch origin morrowglass-dev
if errorlevel 1 goto :failed

git checkout morrowglass-dev
if errorlevel 1 goto :failed

git pull --ff-only origin morrowglass-dev
if errorlevel 1 goto :failed

echo [2/3] Syncing dependencies...
where uv >nul 2>nul
if not errorlevel 1 (
    uv sync --frozen --python 3.11
    if errorlevel 1 goto :failed
) else if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -m pip install --upgrade uv
    if errorlevel 1 goto :failed
    ".venv\Scripts\python.exe" -m uv sync --frozen --python 3.11
    if errorlevel 1 goto :failed
) else (
    echo [ERROR] uv is missing. Run setup_morrowglass_windows.bat first.
    pause
    exit /b 1
)

echo [3/3] Update complete.
echo.
echo Launch with morrowglass_webui.bat
echo.
pause
exit /b 0

:failed
echo.
echo [ERROR] Update failed. Nothing else will be changed.
echo.
pause
exit /b 1
