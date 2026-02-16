@echo off
echo ========================================
echo   Brand Guardian - One-time Setup
echo ========================================
echo.

cd /d "%~dp0"

if not exist ".venv" (
    echo [1/4] Creating virtual environment...
    python -m venv .venv
    if errorlevel 1 (
        echo ERROR: Failed to create venv. Is Python 3.10+ installed?
        pause
        exit /b 1
    )
) else (
    echo [1/4] Virtual environment already exists.
)

echo [2/4] Activating venv and installing dependencies...
call .venv\Scripts\activate.bat
pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: pip install failed.
    pause
    exit /b 1
)

if not exist "knowledge_base" (
    echo [3/4] Creating knowledge_base folder...
    mkdir knowledge_base
    echo       Add your compliance PDF files to knowledge_base\
) else (
    echo [3/4] knowledge_base folder exists.
)

echo [4/4] Pulling Mistral model (Ollama)...
ollama pull mistral 2>nul
if errorlevel 1 (
    echo       WARNING: Could not pull mistral. Make sure Ollama is installed.
    echo       Run: ollama serve
    echo       Then: ollama pull mistral
) else (
    echo       Mistral model ready.
)

echo.
echo ========================================
echo   Setup complete!
echo ========================================
echo.
echo Next steps:
echo   1. Add PDF files to knowledge_base\
echo   2. Run start.bat
echo.
echo In a SEPARATE terminal, run: ollama serve
echo.
pause
