@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
  echo Run Setup-Windows.cmd first.
  pause
  exit /b 1
)
start "UltraEnhance AI" ".venv\Scripts\pythonw.exe" "main.py"
