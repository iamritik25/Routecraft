"""
Train a scikit-learn GradientBoostingRegressor as a lightweight ML backend
for RouteCraft traffic prediction. Runs with only sklearn + pandas + joblib
(all already installed). Saves models/traffic_sklearn.pkl.

Usage:
    python train_sklearn_model.py
"""
import json
import os
import sys

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder

CSV_PATH = os.path.join("data", "Banglore_traffic_Dataset.csv")
OUT_DIR = "models"
OUT_PKL = os.path.join(OUT_DIR, "traffic_sklearn.pkl")
OUT_JSON = os.path.join(OUT_DIR, "traffic_sklearn_metrics.json")

TARGET = "Traffic Volume"   # proxy for congestion; used as TTI surrogate

CATEGORICAL = ["Area Name", "Road/Intersection Name", "Weather Conditions"]
NUMERIC = ["dayofweek", "month", "is_weekend", "roadwork_flag"]


def main():
    if not os.path.exists(CSV_PATH):
        print(f"[ERROR] Dataset not found: {CSV_PATH}")
        sys.exit(1)

    print(f"Loading dataset: {CSV_PATH}")
    df = pd.read_csv(CSV_PATH)
    print(f"  Rows: {len(df)}, Columns: {list(df.columns)}")

    # Date features
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df["dayofweek"] = df["Date"].dt.dayofweek.fillna(0).astype(int)
    df["month"] = df["Date"].dt.month.fillna(1).astype(int)
    df["is_weekend"] = (df["dayofweek"] >= 5).astype(int)

    # Roadwork flag
    roadwork_col = next(
        (c for c in df.columns if "roadwork" in c.lower() or "construction" in c.lower()),
        None,
    )
    if roadwork_col:
        df["roadwork_flag"] = (
            df[roadwork_col].astype(str).str.lower().isin(["yes", "true", "1"])
        ).astype(int)
    else:
        df["roadwork_flag"] = 0

    # Target — try Travel Time Index first, fall back to Traffic Volume normalised
    if "Travel Time Index" in df.columns:
        df["target"] = pd.to_numeric(df["Travel Time Index"], errors="coerce")
        print("  Target: Travel Time Index")
    elif "Traffic Volume" in df.columns:
        vol = pd.to_numeric(df["Traffic Volume"], errors="coerce")
        # Normalise to ~[1.0, 2.0] range matching TTI semantics
        vmin, vmax = vol.min(), vol.max()
        df["target"] = 1.0 + (vol - vmin) / max(vmax - vmin, 1) * 1.0
        print("  Target: Traffic Volume (normalised to TTI range)")
    else:
        print(f"[ERROR] No usable target column. Available: {list(df.columns)}")
        sys.exit(1)

    df = df.dropna(subset=["target"])

    # Encode categoricals
    encoders = {}
    feat_cols = []
    for col in CATEGORICAL:
        if col not in df.columns:
            continue
        enc = LabelEncoder()
        df[col + "_enc"] = enc.fit_transform(df[col].astype(str).fillna("Unknown"))
        encoders[col] = enc
        feat_cols.append(col + "_enc")

    feat_cols += NUMERIC
    for c in NUMERIC:
        if c not in df.columns:
            df[c] = 0

    X = df[feat_cols].values
    y = df["target"].values

    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.2, random_state=42)

    print(f"Training GradientBoostingRegressor on {len(X_tr)} samples...")
    model = GradientBoostingRegressor(
        n_estimators=200,
        learning_rate=0.05,
        max_depth=5,
        random_state=42,
        subsample=0.8,
    )
    model.fit(X_tr, y_tr)

    preds_te = model.predict(X_te)
    baseline_mae = mean_absolute_error(y_te, np.full_like(y_te, y_tr.mean()))
    test_mae = mean_absolute_error(y_te, preds_te)
    test_r2 = r2_score(y_te, preds_te)

    print(f"  Baseline MAE : {baseline_mae:.4f}")
    print(f"  Test MAE     : {test_mae:.4f}  ({(1 - test_mae/baseline_mae)*100:.1f}% better than baseline)")
    print(f"  Test R²      : {test_r2:.4f}")

    os.makedirs(OUT_DIR, exist_ok=True)

    bundle = {
        "model": model,
        "encoders": encoders,
        "feature_cols": feat_cols,
        "categorical": [c for c in CATEGORICAL if c in df.columns],
        "numeric": NUMERIC,
        "target_range": [float(y.min()), float(y.max())],
        "target_mean": float(y.mean()),
    }
    joblib.dump(bundle, OUT_PKL)
    print(f"  Saved: {OUT_PKL}")

    metrics = {
        "model": "sklearn_gbm",
        "n_train": len(X_tr),
        "n_test": len(X_te),
        "baseline_mae": round(baseline_mae, 4),
        "test_mae": round(test_mae, 4),
        "test_r2": round(test_r2, 4),
    }
    with open(OUT_JSON, "w") as f:
        json.dump(metrics, f, indent=2)
    print(f"  Metrics: {OUT_JSON}")
    print("Done!")


if __name__ == "__main__":
    main()
