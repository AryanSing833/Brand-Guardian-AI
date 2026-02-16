@echo off
cd /d "%~dp0"

echo Starting Brand Guardian...
echo.

if not exist ".venv" (
    echo ERROR: Virtual environment not found.
    echo Run setup.bat first.
    pause
    exit /b 1
)

call .venv\Scripts\activate.bat

if not exist "knowledge_base" (
    echo WARNING: knowledge_base folder missing. Creating it...
    mkdir knowledge_base
    echo Add compliance PDF files to knowledge_base\ and restart.
    echo.
)

echo Open http://localhost:8000 in your browser
echo Press Ctrl+C to stop
echo.

uvicorn main:app --host 0.0.0.0 --port 8000 --reload
