@echo off
REM ============================================================
REM  RouteCraft — Start Airflow Scheduler + Webserver
REM  Run this in a separate terminal alongside run.bat
REM ============================================================

call .venv\Scripts\activate.bat

set AIRFLOW_HOME=%CD%\.airflow
set AIRFLOW__CORE__DAGS_FOLDER=%CD%\dags
set AIRFLOW__CORE__LOAD_EXAMPLES=False
set AIRFLOW__CORE__EXECUTOR=SequentialExecutor

echo  Starting Airflow webserver on http://127.0.0.1:8080 ...
echo  Starting Airflow scheduler (cache warms every 30 min) ...
echo  Login: admin / admin
echo  Press Ctrl+C to stop.
echo.

REM Start scheduler in background, webserver in foreground
start "Airflow Scheduler" /min airflow scheduler
airflow webserver --port 8080
