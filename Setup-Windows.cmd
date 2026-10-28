@echo off
setlocal
cd /d "%~dp0"
py -3.11 -m venv .venv
if errorlevel 1 goto fail
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto fail
echo Setup complete. Double-click Launch-UltraEnhance.cmd to open the application.
pause
exit /b 0
:fail
echo Setup failed. Install 64-bit Python 3.11 and check the error above.
pause
exit /b 1
