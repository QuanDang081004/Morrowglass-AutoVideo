@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

echo.
echo ============================================================
echo   MORROWGLASS - LOCAL MACHINE SELF TEST
echo ============================================================
echo.

set "UV_RUN="
where uv >nul 2>nul
if not errorlevel 1 set "UV_RUN=uv run --python 3.11"

if not defined UV_RUN if exist ".venv\Scripts\python.exe" (
    set "UV_RUN=".venv\Scripts\python.exe""
)

if not defined UV_RUN (
    echo [FAIL] Morrowglass Python environment is not ready.
    echo Run setup_morrowglass_windows.bat first.
    echo.
    pause
    exit /b 1
)

set "EN_PY=C:\MorrowglassTTS\venv\Scripts\python.exe"
set "VI_PY=D:\Kokoro-Vietnamese\venv\Scripts\python.exe"

if defined MORROWGLASS_KOKORO_EN_PYTHON set "EN_PY=%MORROWGLASS_KOKORO_EN_PYTHON%"
if defined MORROWGLASS_KOKORO_VI_PYTHON set "VI_PY=%MORROWGLASS_KOKORO_VI_PYTHON%"

set "TEST_DIR=%CD%\storage\morrowglass\machine-test"
if not exist "%TEST_DIR%" mkdir "%TEST_DIR%"

echo [1/4] Core environment...
%UV_RUN% morrowglass.py doctor --kokoro-en-python "%EN_PY%" --kokoro-vi-python "%VI_PY%"
if errorlevel 1 (
    echo.
    echo [FAIL] Core environment check failed.
    echo.
    pause
    exit /b 1
)

echo.
echo [2/4] English Kokoro...
if not exist "%EN_PY%" (
    echo [FAIL] English Kokoro Python not found:
    echo        %EN_PY%
    echo.
    pause
    exit /b 1
)

> "%TEST_DIR%\english.txt" echo Somewhere beyond the village, a forgotten story is waiting to be told.

"%EN_PY%" "%CD%\tools\kokoro_local_bridge.py" ^
  --engine english ^
  --text-file "%TEST_DIR%\english.txt" ^
  --output "%TEST_DIR%\english.wav" ^
  --voice am_michael ^
  --speed 1.0
if errorlevel 1 (
    echo.
    echo [FAIL] English Kokoro synthesis failed.
    echo.
    pause
    exit /b 1
)
if not exist "%TEST_DIR%\english.wav" (
    echo [FAIL] English WAV was not created.
    pause
    exit /b 1
)
for %%A in ("%TEST_DIR%\english.wav") do if %%~zA LEQ 44 (
    echo [FAIL] English WAV is empty.
    pause
    exit /b 1
)
echo [PASS] English Kokoro generated english.wav

echo.
echo [3/4] Vietnamese Kokoro...
if not exist "%VI_PY%" (
    echo [FAIL] Vietnamese Kokoro Python not found:
    echo        %VI_PY%
    echo.
    pause
    exit /b 1
)

> "%TEST_DIR%\vietnamese.txt" echo Xin chao. Day la bai kiem tra giong doc tieng Viet cho Morrowglass.

"%VI_PY%" "%CD%\tools\kokoro_local_bridge.py" ^
  --engine vietnamese ^
  --text-file "%TEST_DIR%\vietnamese.txt" ^
  --output "%TEST_DIR%\vietnamese.wav" ^
  --voice manh_dung ^
  --device cpu
if errorlevel 1 (
    echo.
    echo [FAIL] Vietnamese Kokoro synthesis failed.
    echo.
    pause
    exit /b 1
)
if not exist "%TEST_DIR%\vietnamese.wav" (
    echo [FAIL] Vietnamese WAV was not created.
    pause
    exit /b 1
)
for %%A in ("%TEST_DIR%\vietnamese.wav") do if %%~zA LEQ 44 (
    echo [FAIL] Vietnamese WAV is empty.
    pause
    exit /b 1
)
echo [PASS] Vietnamese Kokoro generated vietnamese.wav

echo.
echo [4/4] Morrowglass CLI import...
%UV_RUN% -c "from app.morrowglass.pipeline import MorrowglassPipeline; from app.morrowglass.audio import VIETNAMESE_KOKORO_VOICES; print('PIPELINE OK', len(VIETNAMESE_KOKORO_VOICES), 'VI voices')"
if errorlevel 1 (
    echo.
    echo [FAIL] Morrowglass pipeline import failed.
    echo.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo   ALL LOCAL MACHINE TESTS PASSED
echo ============================================================
echo.
echo English preview:
echo   %TEST_DIR%\english.wav
echo Vietnamese preview:
echo   %TEST_DIR%\vietnamese.wav
echo.
echo Next step:
echo   Double-click morrowglass_webui.bat
echo.
pause
exit /b 0
