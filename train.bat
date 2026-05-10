@echo off
REM ============================================================
REM  RouteCraft — TRAIN ML MODEL
REM  Trains the scikit-learn GBM on the Bangalore traffic dataset.
REM  Output: models\traffic_sklearn.pkl
REM ============================================================

if not exist ".venv\Scripts\activate.bat" (
    echo  [ERROR] .venv not found. Run setup.bat first.
    pause
    exit /b 1
)

call .venv\Scripts\activate.bat
echo  Training scikit-learn GBM model...
python train_sklearn_model.py
echo.
echo  Done! Model saved to models\traffic_sklearn.pkl
pause
