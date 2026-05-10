@echo off
REM ============================================================
REM  RouteCraft — ONE-TIME SETUP
REM  Creates a local .venv inside the project folder.
REM  Everything stays here — delete the folder, delete it all.
REM ============================================================

echo.
echo  RouteCraft Setup
echo  ================
echo  This will create a .venv folder inside the project.
echo  Nothing will be installed globally on your PC.
echo.

REM Check Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python not found. Install Python 3.10+ from https://python.org
    pause
    exit /b 1
)

REM Create virtual environment inside project folder
if not exist ".venv" (
    echo  [1/4] Creating local virtual environment in .venv ...
    python -m venv .venv
    echo  Done.
) else (
    echo  [1/4] .venv already exists, skipping creation.
)

REM Activate and upgrade pip silently
echo  [2/4] Upgrading pip inside .venv ...
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip --quiet

REM Install all project dependencies into .venv
echo  [3/4] Installing dependencies into .venv (this takes ~2 min on first run) ...
pip install -r requirements.txt --quiet

REM Copy .env.example -> .env if not already present
echo  [4/4] Setting up .env config file ...
if not exist ".env" (
    copy .env.example .env >nul
    echo  Created .env from template. Edit it if needed.
) else (
    echo  .env already exists, skipping.
)

echo.
echo  ============================================================
echo   Setup complete!
echo  ============================================================
echo   To start the server, run:
echo       run.bat
echo.
echo   To activate the environment manually:
echo       .venv\Scripts\activate
echo  ============================================================
echo.
pause
