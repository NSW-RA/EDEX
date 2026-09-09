@echo off
REM ==================================================================
REM  EDEX one-time setup — run this ONCE on a new machine.
REM  Creates the virtual environment and installs the Python packages.
REM  After it finishes, use run_edex.bat to start EDEX.
REM ==================================================================
cd /d "%~dp0"

echo [1/2] Creating the virtual environment...
python -m venv .venv || (echo Could not create venv. Is Python installed? & pause & exit /b 1)

echo [2/2] Installing Python packages...
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements-local.txt || (echo Package install failed. & pause & exit /b 1)

echo.
echo Setup complete. Double-click run_edex.bat to start EDEX.
pause
