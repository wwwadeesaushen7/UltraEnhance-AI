@echo off
setlocal
cd /d "%~dp0"
set "ULTRAENHANCE_SETUP_MODE=%~1"
if exist ".venv\Scripts\python.exe" goto verify_venv

rem Prefer an installed Python 3.12, then 3.11. Never install another runtime.
for %%V in (3.12 3.11) do (
  py -%%V -c "import struct; raise SystemExit(0 if struct.calcsize('P') == 8 else 1)" >nul 2>&1
  if not errorlevel 1 (
    echo Creating the environment with Python %%V...
    py -%%V -m venv .venv
    if errorlevel 1 goto fail
    goto verify_venv
  )
)

rem Also support installations that provide python.exe without the py launcher.
python -c "import sys, struct; raise SystemExit(0 if sys.version_info[:2] in ((3, 11), (3, 12)) and struct.calcsize('P') == 8 else 1)" >nul 2>&1
if errorlevel 1 goto missing_python
python -m venv .venv
if errorlevel 1 goto fail

:verify_venv
".venv\Scripts\python.exe" -c "import sys, struct; raise SystemExit(0 if sys.version_info[:2] in ((3, 11), (3, 12)) and struct.calcsize('P') == 8 else 1)" >nul 2>&1
if errorlevel 1 goto invalid_venv
".venv\Scripts\python.exe" --version
if "%ULTRAENHANCE_SETUP_MODE%"=="--venv-only" exit /b 0
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto fail
echo Setup complete. Double-click Launch-UltraEnhance.cmd to open the application.
pause
exit /b 0

:missing_python
echo No supported 64-bit Python was detected. Use Python 3.12 or 3.11.
echo If Python is already installed, check that its launcher or python.exe is available.
goto fail

:invalid_venv
echo The existing .venv is broken or uses an unsupported Python version.
echo Rename the .venv folder and run Setup-Windows.cmd again.

:fail
echo Setup failed. Review the error above.
if not "%ULTRAENHANCE_SETUP_MODE%"=="--venv-only" pause
exit /b 1
