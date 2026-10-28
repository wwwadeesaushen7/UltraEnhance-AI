@echo off
setlocal
cd /d "%~dp0"
set "ULTRAENHANCE_SETUP_FLAGS="
if "%~1"=="--venv-only" set "ULTRAENHANCE_SETUP_FLAGS=-VenvOnly"
if "%~2"=="--no-prompt" set "ULTRAENHANCE_SETUP_FLAGS=%ULTRAENHANCE_SETUP_FLAGS% -NoPrompt"
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -STA -ExecutionPolicy Bypass -File "%~dp0scripts\setup-windows.ps1" %ULTRAENHANCE_SETUP_FLAGS%
set "ULTRAENHANCE_SETUP_EXIT=%ERRORLEVEL%"
if not "%ULTRAENHANCE_SETUP_EXIT%"=="0" echo Setup failed. Review the message above and setup-diagnostics.txt.
if not "%~1"=="--venv-only" pause
exit /b %ULTRAENHANCE_SETUP_EXIT%
