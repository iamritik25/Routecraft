"""
RouteCraft — Airflow DAG: ML Model Retrainer
=============================================
Runs daily at 2 AM. Checks for data drift in the traffic ML model.
If drift is detected, retrains and hot-reloads the model without
restarting the Flask server.

Schedule: Daily at 02:00 AM
Tasks:
  1. check_drift       → Compare recent predictions vs training distribution
  2. retrain_model     → Retrain sklearn GBM on latest Bangalore traffic data
  3. validate_model    → Smoke-test new model on holdout set (RMSE threshold)
  4. swap_model        → Atomically replace model file (zero-downtime reload)
  5. invalidate_cache  → Clear stale graph cache so Flask rebuilds with new model
"""

from __future__ import annotations

import os
import sys
import logging
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.utils.dates import days_ago

DEFAULT_ARGS = {
    "owner": "routecraft",
    "depends_on_past": False,
    "email_on_failure": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_PATH   = os.path.join(PROJECT_ROOT, "models", "traffic_sklearn.pkl")
STAGING_PATH = os.path.join(PROJECT_ROOT, "models", "traffic_sklearn.staging.pkl")
DRIFT_LOG    = os.path.join(PROJECT_ROOT, "models", "drift_log.json")
CACHE_DIR    = os.path.join(PROJECT_ROOT, ".graph_cache")

RMSE_THRESHOLD = 8.0   # minutes — retrained model must beat this to be swapped in


# ---------------------------------------------------------------------------
# Task 1: Check for data drift
# ---------------------------------------------------------------------------
def check_drift(**context) -> bool:
    """
    Use the drift_monitor module to compare recent traffic predictions
    against the training distribution. Pushes drift_detected to XCom.
    """
    sys.path.insert(0, PROJECT_ROOT)
    try:
        from drift_monitor import DriftMonitor
        monitor = DriftMonitor(model_path=MODEL_PATH, drift_log=DRIFT_LOG)
        result  = monitor.run()
        drift   = result.get("drift_detected", False)
        score   = result.get("drift_score", 0.0)
        logging.info(f"[airflow:drift] drift_detected={drift}, score={score:.4f}")
    except Exception as e:
        logging.warning(f"[airflow:drift] Monitor failed ({e}) — assuming no drift")
        drift = False

    context["ti"].xcom_push(key="drift_detected", value=drift)
    return drift


# ---------------------------------------------------------------------------
# Task 2: Retrain the model (only runs if drift detected)
# ---------------------------------------------------------------------------
def retrain_model(**context) -> str:
    """
    Re-run the full sklearn GBM training pipeline.
    Saves output to staging path so the current live model is untouched.
    """
    drift = context["ti"].xcom_pull(task_ids="check_drift", key="drift_detected")
    if not drift:
        logging.info("[airflow:retrain] No drift detected — skipping retrain")
        return "skipped"

    sys.path.insert(0, PROJECT_ROOT)
    import importlib
    import train_sklearn_model as trainer

    logging.info("[airflow:retrain] Drift detected — starting retraining ...")
    os.makedirs(os.path.dirname(STAGING_PATH), exist_ok=True)

    try:
        # Re-import to pick up any code changes
        importlib.reload(trainer)
        trainer.train_and_save(output_path=STAGING_PATH)
        logging.info(f"[airflow:retrain] New model saved to {STAGING_PATH}")
        return "trained"
    except Exception as e:
        raise RuntimeError(f"[airflow:retrain] Training failed: {e}") from e


# ---------------------------------------------------------------------------
# Task 3: Validate the newly trained model
# ---------------------------------------------------------------------------
def validate_model(**context) -> float:
    """
    Run the staging model on a holdout set.
    Fails the DAG if RMSE exceeds RMSE_THRESHOLD (protects production).
    """
    import pickle
    import numpy as np

    if not os.path.exists(STAGING_PATH):
        logging.info("[airflow:validate_model] No staging model — skip validation")
        return 0.0

    sys.path.insert(0, PROJECT_ROOT)
    from train_sklearn_model import build_holdout_set

    with open(STAGING_PATH, "rb") as f:
        model = pickle.load(f)

    X_test, y_test = build_holdout_set()
    y_pred = model.predict(X_test)
    rmse = float(np.sqrt(((y_pred - y_test) ** 2).mean()))

    logging.info(f"[airflow:validate_model] Staging RMSE = {rmse:.3f} min (threshold={RMSE_THRESHOLD})")

    if rmse > RMSE_THRESHOLD:
        raise ValueError(
            f"[airflow:validate_model] Model RMSE {rmse:.2f} exceeds threshold "
            f"{RMSE_THRESHOLD} — not swapping to production"
        )

    context["ti"].xcom_push(key="staging_rmse", value=rmse)
    return rmse


# ---------------------------------------------------------------------------
# Task 4: Atomic model swap (zero-downtime)
# ---------------------------------------------------------------------------
def swap_model(**context) -> None:
    """
    Atomically rename staging -> production using os.replace()
    (atomic on POSIX/NTFS — Flask reads the new file on next request
    without needing a restart, because traffic_ml.py uses lazy loading).
    """
    if not os.path.exists(STAGING_PATH):
        logging.info("[airflow:swap_model] No staging model — nothing to swap")
        return

    # Backup old model with timestamp
    if os.path.exists(MODEL_PATH):
        ts      = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        backup  = MODEL_PATH.replace(".pkl", f".backup_{ts}.pkl")
        os.rename(MODEL_PATH, backup)
        logging.info(f"[airflow:swap_model] Old model backed up → {backup}")

    os.replace(STAGING_PATH, MODEL_PATH)
    logging.info(f"[airflow:swap_model] New model swapped in → {MODEL_PATH}")


# ---------------------------------------------------------------------------
# Task 5: Invalidate stale graph cache
# ---------------------------------------------------------------------------
def invalidate_cache(**context) -> None:
    """
    After model swap, clear all cached graphs so Flask rebuilds them
    with the new traffic predictions on the next request cycle.
    The cache_warmer DAG will re-populate them within 30 minutes.
    """
    if not os.path.exists(STAGING_PATH) and not context["ti"].xcom_pull(
        task_ids="retrain_model"
    ):
        logging.info("[airflow:invalidate] Model unchanged — keeping cache intact")
        return

    sys.path.insert(0, PROJECT_ROOT)
    from disk_cache import DiskCache

    cache = DiskCache(CACHE_DIR)
    cleared = cache.clear_all()
    logging.info(f"[airflow:invalidate] Cleared {cleared} stale graph cache entries")


# ---------------------------------------------------------------------------
# DAG definition
# ---------------------------------------------------------------------------
with DAG(
    dag_id="routecraft_ml_retrainer",
    description="Daily ML model drift check + conditional retrain + zero-downtime swap",
    default_args=DEFAULT_ARGS,
    schedule_interval="0 2 * * *",   # 2:00 AM daily
    start_date=days_ago(1),
    catchup=False,
    max_active_runs=1,
    tags=["routecraft", "ml", "retraining", "mlops"],
) as dag:

    t1 = PythonOperator(task_id="check_drift",      python_callable=check_drift)
    t2 = PythonOperator(task_id="retrain_model",    python_callable=retrain_model)
    t3 = PythonOperator(task_id="validate_model",   python_callable=validate_model)
    t4 = PythonOperator(task_id="swap_model",       python_callable=swap_model)
    t5 = PythonOperator(task_id="invalidate_cache", python_callable=invalidate_cache)

    t1 >> t2 >> t3 >> t4 >> t5
