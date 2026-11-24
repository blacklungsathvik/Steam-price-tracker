@echo off
cd /d "%~dp0"
echo Setting up (first run only)...
if not exist .venv\Scripts\python.exe py -3 -m venv .venv
if not exist .venv\Scripts\python.exe python -m venv .venv
call .venv\Scripts\activate.bat
pip install -q -r requirements.txt
echo.
echo Open http://localhost:8000 in your browser.  Press Ctrl+C to stop.
python run.py
pause
