@echo off
REM ============================================================
REM  RouteCraft — START SERVER
REM  Activates local .venv and runs the Flask app.
REM  Run setup.bat first if you haven't already.
REM ============================================================

if not exist ".venv\Scripts\activate.bat" (
    echo  [ERROR] .venv not found. Run setup.bat first.
    pause
    exit /b 1
)

echo.
echo  Activating local environment...
call .venv\Scripts\activate.bat

REM Load .env variables into this session
if exist ".env" (
    echo  Loading .env config...
    for /f "usebackq tokens=1,* delims==" %%A in (".env") do (
        REM Skip comments and blank lines
        if not "%%A"=="" if not "%%A:~0,1%"=="#" (
            set "%%A=%%B"
        )
    )
)

echo  Starting RouteCraft on http://127.0.0.1:5000
echo  Press Ctrl+C to stop.
echo.
python app.py
