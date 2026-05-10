"""
Training entry-point for the RouteCraft traffic ML model.

Trains BOTH backends and saves them to `models/`:

  1. LightGBM regressor (CPU, best accuracy on tabular data)
  2. PyTorch MLP on Apple Silicon MPS GPU (demonstration of Metal support)

Usage:
    python train_traffic_model.py [--csv PATH] [--epochs N]

Artifacts written:
    models/traffic_lgbm.pkl
    models/traffic_lgbm_metrics.json
    models/traffic_mps.pt
    models/traffic_mps_preproc.pkl
    models/traffic_mps_metrics.json
    models/feature_importance.png
    models/comparison.json
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

import matplotlib
import mlflow

matplotlib.use("Agg")  # headless
import matplotlib.pyplot as plt

from services.traffic_ml import train_lightgbm, train_pytorch_mps


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", default="data/Banglore_traffic_Dataset.csv",
                        help="Path to the Bangalore traffic CSV")
    parser.add_argument("--out", default="models", help="Output directory")
    parser.add_argument("--epochs", type=int, default=120,
                        help="Epochs for the PyTorch MPS model")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent
    csv_path = str(project_root / args.csv) if not os.path.isabs(args.csv) else args.csv
    out_dir = str(project_root / args.out) if not os.path.isabs(args.out) else args.out
    os.makedirs(out_dir, exist_ok=True)

    print(f"=== RouteCraft traffic ML trainer ===")
    print(f"CSV:    {csv_path}")
    print(f"Output: {out_dir}\n")

    # Set up MLflow
    mlflow.set_tracking_uri("sqlite:///mlruns.db")
    mlflow.set_experiment("routecraft_traffic_model")

    with mlflow.start_run(run_name="batch_training"):
        # Log input data path
        mlflow.log_param("csv_path", csv_path)
        
        # --- LightGBM ---
        print("[1/2] Training LightGBM...")
        t0 = time.time()
        lgbm_metrics = train_lightgbm(csv_path, out_dir)
        lgbm_metrics["train_seconds"] = round(time.time() - t0, 2)
        print(f"      train_mae  = {lgbm_metrics['train_mae']:.4f}")
        print(f"      test_mae   = {lgbm_metrics['test_mae']:.4f}")
        print(f"      baseline   = {lgbm_metrics['baseline_mae']:.4f}")
        print(f"      test_r2    = {lgbm_metrics['test_r2']:.4f}")
        print(f"      time       = {lgbm_metrics['train_seconds']}s\n")
        
        mlflow.log_metrics({
            "lgbm_train_mae": lgbm_metrics["train_mae"],
            "lgbm_test_mae": lgbm_metrics["test_mae"],
            "lgbm_test_r2": lgbm_metrics["test_r2"],
            "lgbm_train_time_s": lgbm_metrics["train_seconds"]
        })

        # --- PyTorch MPS ---
        print("[2/2] Training PyTorch MLP...")
        t0 = time.time()
        mps_metrics = train_pytorch_mps(csv_path, out_dir, epochs=args.epochs)
        mps_metrics["train_seconds"] = round(time.time() - t0, 2)
        print(f"      device     = {mps_metrics['device']}")
        print(f"      train_mae  = {mps_metrics['train_mae']:.4f}")
        print(f"      test_mae   = {mps_metrics['test_mae']:.4f}")
        print(f"      baseline   = {mps_metrics['baseline_mae']:.4f}")
        print(f"      test_r2    = {mps_metrics['test_r2']:.4f}")
        print(f"      time       = {mps_metrics['train_seconds']}s\n")

        mlflow.log_param("mps_epochs", args.epochs)
        mlflow.log_metrics({
            "mps_train_mae": mps_metrics["train_mae"],
            "mps_test_mae": mps_metrics["test_mae"],
            "mps_test_r2": mps_metrics["test_r2"],
            "mps_train_time_s": mps_metrics["train_seconds"]
        })

        # --- Feature importance chart (LightGBM) ---
        fi = lgbm_metrics["feature_importance"]
        names, vals = zip(*sorted(fi.items(), key=lambda kv: kv[1], reverse=True))
        plt.figure(figsize=(8, 4))
        plt.barh(names[::-1], vals[::-1])
        plt.title("LightGBM feature importance (Travel Time Index)")
        plt.tight_layout()
        fi_path = os.path.join(out_dir, "feature_importance.png")
        plt.savefig(fi_path, dpi=130)
        plt.close()
        print(f"Feature importance chart saved: {fi_path}")

        # --- Summary JSON ---
        summary = {
            "lightgbm": lgbm_metrics,
            "pytorch_mps": mps_metrics,
            "recommended": "lightgbm" if lgbm_metrics["test_mae"] <= mps_metrics["test_mae"] else "mps_nn",
            "baseline_mae": lgbm_metrics["baseline_mae"]
        }
        with open(os.path.join(out_dir, "comparison.json"), "w") as f:
            json.dump(summary, f, indent=2)

        # Log metrics and artifacts
        mlflow.log_metric("baseline_mae", summary["baseline_mae"])
        mlflow.log_param("recommended_backend", summary["recommended"])
        
        mlflow.log_artifact(fi_path)
        mlflow.log_artifact(os.path.join(out_dir, "comparison.json"))
        mlflow.log_artifact(os.path.join(out_dir, "traffic_lgbm.pkl"))
        if os.path.exists(os.path.join(out_dir, "traffic_mps.pt")):
            mlflow.log_artifact(os.path.join(out_dir, "traffic_mps.pt"))

    # --- Winner ---
    print("\n=== Results ===")
    print(f"LightGBM   test MAE: {lgbm_metrics['test_mae']:.4f} (baseline {lgbm_metrics['baseline_mae']:.4f})")
    print(f"MPS NN     test MAE: {mps_metrics['test_mae']:.4f}")
    print(f"Recommended backend: {summary['recommended']}")
    print(f"\nTo use the MPS model at runtime:  TRAFFIC_MODEL_TYPE=mps_nn python app.py")
    print(f"To use LightGBM (default):        python app.py")
    print(f"\nTo view MLflow dashboard run:     mlflow ui --backend-store-uri sqlite:///mlruns.db")


if __name__ == "__main__":
    main()
