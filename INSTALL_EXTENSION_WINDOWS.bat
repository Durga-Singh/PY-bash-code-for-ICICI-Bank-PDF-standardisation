@echo off
setlocal
cd /d "%~dp0"
if exist .venv\Scripts\python.exe goto install
where py >nul 2>nul
if not errorlevel 1 (
 py -3 -m venv .venv
) else (
 python -m venv .venv
)
if errorlevel 1 goto failed
:install
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto failed
.venv\Scripts\python.exe install_extension.py
if errorlevel 1 goto failed
echo.
echo Keep this extracted folder in its current location.
echo Read EXTENSION_SETUP.md for the remaining browser step.
pause
exit /b 0
:failed
echo Setup failed. Install Python 3.11 or 3.12 from python.org with Add Python to PATH.
echo Internet is required for initial dependency installation.
pause
exit /b 1
