@echo off
REM ============================================================
REM  RouteCraft — Airflow Setup (inside .venv, nothing global)
REM  Run setup.bat first, then this.
REM ============================================================

if not exist ".venv\Scripts\activate.bat" (
    echo  [ERROR] Run setup.bat first to create .venv
    pause & exit /b 1
)

call .venv\Scripts\activate.bat

echo.
echo  [1/4] Installing Apache Airflow into .venv ...
echo  (This is ~500MB and takes 3-5 minutes on first run)
pip install "apache-airflow>=2.8" --constraint "https://raw.githubusercontent.com/apache/airflow/constraints-2.8.4/constraints-3.12.txt" --quiet

echo  [2/4] Setting up Airflow home inside project ...
set AIRFLOW_HOME=%CD%\.airflow
set AIRFLOW__CORE__DAGS_FOLDER=%CD%\dags
set AIRFLOW__CORE__LOAD_EXAMPLES=False
set AIRFLOW__CORE__EXECUTOR=SequentialExecutor

echo  [3/4] Initialising Airflow DB (SQLite, local only) ...
airflow db init

echo  [4/4] Creating admin user ...
airflow users create --username admin --password admin --firstname Subrat --lastname Behera --role Admin --email admin@routecraft.local

echo.
echo  ============================================================
echo   Airflow setup complete!
echo  ============================================================
echo   To start everything:
echo     1. Terminal 1:  run.bat          (Flask server)
echo     2. Terminal 2:  airflow_start.bat (Airflow scheduler + UI)
echo     3. Browser:     http://127.0.0.1:8080  (Airflow UI)
echo     3. Browser:     http://127.0.0.1:5000  (RouteCraft UI)
echo  ============================================================
pause
