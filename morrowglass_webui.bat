@echo off
setlocal
cd /d "%~dp0"
set "CURRENT_DIR=%CD%"
set "PYTHONPATH=%CURRENT_DIR%"

if not defined MORROWGLASS_WEBUI_HOST set "MORROWGLASS_WEBUI_HOST=127.0.0.1"
if not defined MORROWGLASS_WEBUI_PORT set "MORROWGLASS_WEBUI_PORT=8510"

set "STREAMLIT_CMD="
if exist "%CURRENT_DIR%\.venv\Scripts\python.exe" (
    set "STREAMLIT_CMD="%CURRENT_DIR%\.venv\Scripts\python.exe" -m streamlit"
) else if exist "%CURRENT_DIR%\lib\python\python.exe" (
    set "STREAMLIT_CMD="%CURRENT_DIR%\lib\python\python.exe" -m streamlit"
) else (
    where uv >nul 2>nul
    if not errorlevel 1 set "STREAMLIT_CMD=uv run streamlit"
)

if not defined STREAMLIT_CMD (
    where streamlit >nul 2>nul
    if not errorlevel 1 set "STREAMLIT_CMD=streamlit"
)

if not defined STREAMLIT_CMD (
    echo.
    echo [Morrowglass] Python environment is not ready.
    echo Run the MoneyPrinterTurbo setup first, then launch this file again.
    echo.
    pause
    exit /b 1
)

set "SELECTED_PORT="
for /f %%P in ('powershell -NoProfile -ExecutionPolicy Bypass -Command "$preferred=[int]$env:MORROWGLASS_WEBUI_PORT; $candidates=@($preferred)+@(8511..8599); foreach ($port in $candidates) { $listener=$null; try { $listener=[Net.Sockets.TcpListener]::new([Net.IPAddress]::Parse($env:MORROWGLASS_WEBUI_HOST),$port); $listener.Start(); $listener.Stop(); Write-Output $port; exit 0 } catch { if ($null -ne $listener) { try { $listener.Stop() } catch {} } } }; exit 1"') do set "SELECTED_PORT=%%P"

if not defined SELECTED_PORT (
    echo [Morrowglass] No available port found in 8510-8599.
    pause
    exit /b 1
)

set "MORROWGLASS_WEBUI_PORT=%SELECTED_PORT%"
echo.
echo ============================================================
echo   MORROWGLASS AUTOVIDEO
echo   http://%MORROWGLASS_WEBUI_HOST%:%MORROWGLASS_WEBUI_PORT%
echo ============================================================
echo.

%STREAMLIT_CMD% run .\webui\Morrowglass.py --server.address=%MORROWGLASS_WEBUI_HOST% --server.port=%MORROWGLASS_WEBUI_PORT% --browser.serverAddress=%MORROWGLASS_WEBUI_HOST% --browser.gatherUsageStats=False --client.toolbarMode=minimal --logger.hideWelcomeMessage=True --server.showEmailPrompt=False --server.enableCORS=True
