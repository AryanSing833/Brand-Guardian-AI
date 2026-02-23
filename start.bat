@echo off
cd /d "%~dp0"

echo Starting Brand Guardian...
echo.

REM Use venv only if it has uvicorn; otherwise use system Python
if exist ".venv\Scripts\activate.bat" (
    .venv\Scripts\python.exe -c "import uvicorn" 2>nul
    if errorlevel 1 (
        echo Venv missing dependencies, using system Python.
        set SKIP_VENV=1
    ) else (
        call .venv\Scripts\activate.bat
    )
)

if not exist "knowledge_base" (
    echo WARNING: knowledge_base folder missing. Creating it...
    mkdir knowledge_base
    echo Add compliance PDF files to knowledge_base\ and restart.
    echo.
)

echo Open http://localhost:8000 in your browser
echo Press Ctrl+C to stop
echo.

if defined SKIP_VENV (
    REM Use system Python (venv not activated, so 'python' is from PATH)
    python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
) else (
    python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
)
