@echo off
REM ==================================================================
REM  EDEX launcher — double-click this to start the app.
REM  It opens EDEX in your web browser. Keep this window open while
REM  you use it; close the window (or press Ctrl+C) to stop.
REM ==================================================================
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo First-time setup needed. Please run setup_edex.bat once, then use this again.
    pause
    exit /b 1
)

echo Starting EDEX... your browser will open shortly.
".venv\Scripts\python.exe" -m streamlit run app.py

pause
