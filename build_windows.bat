@echo off
setlocal
cd /d "%~dp0"
title SolScribe - Build Windows EXE
where py >nul 2>&1
if %errorlevel%==0 (
  set "PY=py -3.11"
) else (
  set "PY=python"
)
if not exist ".venv\Scripts\python.exe" (
  %PY% -m venv ".venv"
  if errorlevel 1 goto :fail
)
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements-build.txt
if errorlevel 1 goto :fail
".venv\Scripts\python.exe" -m PyInstaller --clean --noconfirm --onedir --windowed --name SolScribe --icon "assets\solscribe.ico" --version-file "assets\version_info.txt" --add-data "assets\solscribe.ico;assets" --add-data "assets\solscribe.png;assets" --add-data "LICENSE;." --add-data "START_HERE.txt;." --collect-all faster_whisper --collect-all ctranslate2 --collect-all tokenizers --collect-all av --collect-all sounddevice --collect-all soundcard app.py
if errorlevel 1 goto :fail
echo.
echo BUILD SUCCESSFUL: dist\SolScribe\SolScribe.exe
echo Keep the entire dist\SolScribe folder together when sharing it.
exit /b 0
:fail
echo.
echo Build failed. Check the messages above.
pause
exit /b 1
