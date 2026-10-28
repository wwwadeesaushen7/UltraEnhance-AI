@echo off
setlocal
cd /d "%~dp0"
call "%~dp0Setup-Windows.cmd" --venv-only
if errorlevel 1 goto fail
".venv\Scripts\python.exe" -m pip install -r requirements-dev.txt
if errorlevel 1 goto fail
set QT_QPA_PLATFORM=offscreen
".venv\Scripts\python.exe" -m pytest -q
if errorlevel 1 goto fail
".venv\Scripts\python.exe" -m PyInstaller --noconfirm UltraEnhance.spec
if errorlevel 1 goto fail
echo Build complete: dist\UltraEnhanceAI\UltraEnhanceAI.exe
echo Distribute the entire UltraEnhanceAI folder.
pause
exit /b 0
:fail
echo Build failed. Review the error above.
pause
exit /b 1
