@echo off
setlocal
cd /d "%~dp0"
title SolScribe - Windows launcher
where py >nul 2>&1
if %errorlevel%==0 (
  set "PY=py -3.11"
) else (
  set "PY=python"
)
if not exist ".venv\Scripts\python.exe" (
  echo [SolScribe] Creating your Python environment...
  %PY% -m venv ".venv"
  if errorlevel 1 goto :fail
)
echo [SolScribe] Checking dependencies...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 goto :fail
echo [SolScribe] Starting desktop app...
".venv\Scripts\python.exe" app.py
if errorlevel 1 goto :fail
exit /b 0
:fail
echo.
echo There was a problem. Check that Python 3.11 (64-bit) is installed.
echo See README.md for the troubleshooting guide.
pause
exit /b 1
