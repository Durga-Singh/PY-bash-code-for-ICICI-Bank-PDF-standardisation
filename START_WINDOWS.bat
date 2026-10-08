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
if exist .venv\ready.txt goto launch
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto failed
.venv\Scripts\python.exe -c "import fitz, reportlab, fontTools, tkinter"
if errorlevel 1 goto failed
echo ready>.venv\ready.txt
:launch
.venv\Scripts\python.exe app.py
if errorlevel 1 goto failed
exit /b
:failed
echo.
echo Setup or launch failed. Install Python 3.11 or 3.12 from python.org,
echo including Tcl/Tk, and enable Add Python to PATH. Internet is needed for first setup.
pause
