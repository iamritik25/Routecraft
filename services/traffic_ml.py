"""
ML-backed traffic multiplier predictor for RouteCraft.

Primary model: LightGBM regressor on the Bangalore Traffic Pulse dataset
(preethamgouda/banglore-city-traffic-dataset). Predicts Travel Time Index
(TTI) from (area, road, day_of_week, month, weather, roadwork).

Secondary model: PyTorch MLP trained on Apple Metal (MPS) GPU. Used when
MODEL_TYPE=mps_nn is selected. Demonstrates GPU-accelerated training on
Apple Silicon (M1/M2/M3).

The predictor is wrapped by `get_ml_multiplier` in traffic_model.py and
falls back to the heuristic when the area is outside the 8 trained areas.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import joblib
import numpy as np
import pandas as pd

# We import these at the top level because they are required for unpickling 
# (joblib.load) and the core prediction logic. If missing, the predictor 
# gracefully handles it via try/except in the _load() method.
try:
    import lightgbm as lgb
except ImportError:
    lgb = None

try:
    import sklearn
    from sklearn.preprocessing import LabelEncoder, StandardScaler
except ImportError:
    LabelEncoder = None
    StandardScaler = None


# The 8 Bangalore areas present in the training dataset.
KNOWN_AREAS: List[str] = [
    "Electronic City",
    "Hebbal",
    "Indiranagar",
    "Jayanagar",
    "Koramangala",
    "M.G. Road",
    "Whitefield",
    "Yeshwanthpur",
]

KNOWN_WEATHERS: List[str] = ["Clear", "Fog", "Overcast", "Rain", "Windy"]

# Aliases used when mapping RouteCraft location names to dataset areas.
# Substring matching is also applied on top of these aliases.
AREA_ALIASES: Dict[str, str] = {
    "mg road": "M.G. Road",
    "m g road": "M.G. Road",
    "m.g.road": "M.G. Road",
    "electronic city": "Electronic City",
    "e city": "Electronic City",
    "silk board": "Koramangala",  # adjacent
    "majestic": "M.G. Road",       # central, closest proxy
    "kempegowda": "M.G. Road",
    "btm": "Koramangala",
    "hsr": "Koramangala",
    "marathahalli": "Whitefield",
    "itpl": "Whitefield",
    "kadugodi": "Whitefield",
    "yeshwantpur": "Yeshwanthpur",
    "yeshwanthpur": "Yeshwanthpur",
    "indiranagar": "Indiranagar",
    "jayanagar": "Jayanagar",
    "jp nagar": "Jayanagar",
    "hebbal": "Hebbal",
    "yelahanka": "Hebbal",
    "airport": "Hebbal",           # BLR airport is north, Hebbal side
    "kengeri": "Yeshwanthpur",     # west, closer to Yeshwanthpur
    "koramangala": "Koramangala",
}


def detect_area(location_name: Optional[str]) -> Optional[str]:
    """
    Map a RouteCraft location name to one of the 8 dataset areas.
    Returns None when no match is found.
    """
    if not location_name:
        return None
    name = location_name.lower().strip()

    for alias, area in AREA_ALIASES.items():
        if alias in name:
            return area

    for area in KNOWN_AREAS:
        if area.lower() in name:
            return area

    return None


def _engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add derived columns used by both the LightGBM and MPS NN models.
    Mutates a copy of the dataframe.
    """
    out = df.copy()
    out["Date"] = pd.to_datetime(out["Date"], errors="coerce")
    out["dayofweek"] = out["Date"].dt.dayofweek
    out["month"] = out["Date"].dt.month
    out["is_weekend"] = (out["dayofweek"] >= 5).astype(int)
    out["roadwork_flag"] = (out["Roadwork and Construction Activity"]
                            .astype(str).str.lower().isin(["yes", "true", "1"])).astype(int)
    return out


# ----------------------------------------------------------------------------
# LightGBM model
# ----------------------------------------------------------------------------

def train_lightgbm(
    csv_path: str,
    output_dir: str,
    random_state: int = 42,
) -> Dict[str, Any]:
    """
    Train a LightGBM regressor on Travel Time Index.
    Saves model + encoders to output_dir and returns metrics.
    """
    import lightgbm as lgb
    from sklearn.metrics import mean_absolute_error, r2_score
    from sklearn.model_selection import train_test_split
    from sklearn.preprocessing import LabelEncoder

    os.makedirs(output_dir, exist_ok=True)

    df = pd.read_csv(csv_path)
    df = _engineer_features(df)

    target_col = "Travel Time Index"
    categorical = ["Area Name", "Road/Intersection Name", "Weather Conditions"]
    numeric = ["dayofweek", "month", "is_weekend", "roadwork_flag"]

    encoders: Dict[str, LabelEncoder] = {}
    for col in categorical:
        le = LabelEncoder()
        df[col + "_enc"] = le.fit_transform(df[col].astype(str))
        encoders[col] = le

    feature_cols = [c + "_enc" for c in categorical] + numeric
    X = df[feature_cols].values
    y = df[target_col].values

    X_tr, X_te, y_tr, y_te = train_test_split(
        X, y, test_size=0.2, random_state=random_state
    )

    model = lgb.LGBMRegressor(
        n_estimators=400,
        learning_rate=0.05,
        num_leaves=31,
        min_child_samples=20,
        random_state=random_state,
        verbose=-1,
    )
    model.fit(X_tr, y_tr)

    preds_tr = model.predict(X_tr)
    preds_te = model.predict(X_te)

    # Baseline: predict mean TTI always (what a dumb model does).
    baseline = np.full_like(y_te, y_tr.mean())

    metrics = {
        "model": "lightgbm",
        "n_train": int(len(X_tr)),
        "n_test": int(len(X_te)),
        "train_mae": float(mean_absolute_error(y_tr, preds_tr)),
        "test_mae": float(mean_absolute_error(y_te, preds_te)),
        "baseline_mae": float(mean_absolute_error(y_te, baseline)),
        "test_r2": float(r2_score(y_te, preds_te)),
        "feature_importance": dict(zip(feature_cols, model.feature_importances_.tolist())),
        "target_range": [float(y.min()), float(y.max())],
        "target_mean": float(y.mean()),
    }

    joblib.dump(
        {
            "model": model,
            "encoders": encoders,
            "feature_cols": feature_cols,
            "categorical": categorical,
            "numeric": numeric,
        },
        os.path.join(output_dir, "traffic_lgbm.pkl"),
    )
    with open(os.path.join(output_dir, "traffic_lgbm_metrics.json"), "w") as f:
        json.dump(metrics, f, indent=2)

    return metrics


# ----------------------------------------------------------------------------
# PyTorch MPS model (Apple Silicon GPU)
# ----------------------------------------------------------------------------

def train_pytorch_mps(
    csv_path: str,
    output_dir: str,
    epochs: int = 120,
    batch_size: int = 128,
    lr: float = 1e-3,
    random_state: int = 42,
) -> Dict[str, Any]:
    """
    Train a small MLP on Apple Silicon's MPS GPU.
    Falls back to CPU if MPS is unavailable.
    """
    import torch
    import torch.nn as nn
    from sklearn.metrics import mean_absolute_error, r2_score
    from sklearn.model_selection import train_test_split
    from sklearn.preprocessing import LabelEncoder, StandardScaler

    os.makedirs(output_dir, exist_ok=True)

    # Device selection — prefer MPS on Apple Silicon.
    if torch.backends.mps.is_available():
        device = torch.device("mps")
        device_name = "mps"
    elif torch.cuda.is_available():
        device = torch.device("cuda")
        device_name = "cuda"
    else:
        device = torch.device("cpu")
        device_name = "cpu"

    torch.manual_seed(random_state)
    np.random.seed(random_state)

    df = pd.read_csv(csv_path)
    df = _engineer_features(df)

    target_col = "Travel Time Index"
    categorical = ["Area Name", "Road/Intersection Name", "Weather Conditions"]
    numeric = ["dayofweek", "month", "is_weekend", "roadwork_flag"]

    encoders: Dict[str, LabelEncoder] = {}
    for col in categorical:
        le = LabelEncoder()
        df[col + "_enc"] = le.fit_transform(df[col].astype(str))
        encoders[col] = le

    cat_enc = np.stack([df[c + "_enc"].values for c in categorical], axis=1).astype(np.float32)
    num_enc = df[numeric].values.astype(np.float32)

    scaler_cat = StandardScaler().fit(cat_enc)
    scaler_num = StandardScaler().fit(num_enc)
    X = np.concatenate([scaler_cat.transform(cat_enc), scaler_num.transform(num_enc)], axis=1).astype(np.float32)
    y = df[target_col].values.astype(np.float32)

    X_tr, X_te, y_tr, y_te = train_test_split(
        X, y, test_size=0.2, random_state=random_state
    )

    X_tr_t = torch.tensor(X_tr, dtype=torch.float32, device=device)
    y_tr_t = torch.tensor(y_tr, dtype=torch.float32, device=device).unsqueeze(1)
    X_te_t = torch.tensor(X_te, dtype=torch.float32, device=device)

    class TTIMlp(nn.Module):
        def __init__(self, in_dim: int):
            super().__init__()
            self.net = nn.Sequential(
                nn.Linear(in_dim, 128),
                nn.ReLU(),
                nn.Dropout(0.1),
                nn.Linear(128, 64),
                nn.ReLU(),
                nn.Linear(64, 1),
            )

        def forward(self, x):
            return self.net(x)

    model = TTIMlp(X.shape[1]).to(device)
    optim = torch.optim.Adam(model.parameters(), lr=lr)
    loss_fn = nn.SmoothL1Loss()

    n = X_tr_t.shape[0]
    for epoch in range(epochs):
        model.train()
        perm = torch.randperm(n, device=device)
        losses = []
        for i in range(0, n, batch_size):
            idx = perm[i : i + batch_size]
            xb = X_tr_t[idx]
            yb = y_tr_t[idx]
            optim.zero_grad()
            pred = model(xb)
            loss = loss_fn(pred, yb)
            loss.backward()
            optim.step()
            losses.append(float(loss.item()))

    model.eval()
    with torch.no_grad():
        preds_te = model(X_te_t).cpu().numpy().ravel()
        preds_tr = model(X_tr_t).cpu().numpy().ravel()

    baseline = np.full_like(y_te, y_tr.mean())

    metrics = {
        "model": "pytorch_mps_mlp",
        "device": device_name,
        "n_train": int(len(X_tr)),
        "n_test": int(len(X_te)),
        "epochs": epochs,
        "train_mae": float(mean_absolute_error(y_tr, preds_tr)),
        "test_mae": float(mean_absolute_error(y_te, preds_te)),
        "baseline_mae": float(mean_absolute_error(y_te, baseline)),
        "test_r2": float(r2_score(y_te, preds_te)),
        "target_range": [float(y.min()), float(y.max())],
        "target_mean": float(y.mean()),
    }

    # Save model state dict + preprocessors.
    torch.save(
        {
            "state_dict": model.state_dict(),
            "in_dim": X.shape[1],
        },
        os.path.join(output_dir, "traffic_mps.pt"),
    )
    joblib.dump(
        {
            "encoders": encoders,
            "scaler_cat": scaler_cat,
            "scaler_num": scaler_num,
            "categorical": categorical,
            "numeric": numeric,
        },
        os.path.join(output_dir, "traffic_mps_preproc.pkl"),
    )
    with open(os.path.join(output_dir, "traffic_mps_metrics.json"), "w") as f:
        json.dump(metrics, f, indent=2)

    return metrics


# ----------------------------------------------------------------------------
# Inference — single class with two backends
# ----------------------------------------------------------------------------

@dataclass
class _LoadedLGBM:
    model: Any
    encoders: Dict[str, Any]
    feature_cols: List[str]
    categorical: List[str]
    numeric: List[str]


@dataclass
class _LoadedMPS:
    torch_model: Any
    encoders: Dict[str, Any]
    scaler_cat: Any
    scaler_num: Any
    categorical: List[str]
    numeric: List[str]
    device: Any


@dataclass
class _LoadedSKLearn:
    model: Any
    encoders: Dict[str, Any]
    feature_cols: List[str]
    categorical: List[str]
    numeric: List[str]


class TrafficPredictor:
    """
    Loads a trained model and provides TTI predictions.
    Call `predict_tti(area, weather, day_of_week, month, road=None)`
    or the higher-level `multiplier_for_segment(...)` used by traffic_model.py.
    """

    def __init__(
        self,
        models_dir: str,
        model_type: str = "lightgbm",
    ):
        self.models_dir = models_dir
        self.model_type = model_type
        self._lgbm: Optional[_LoadedLGBM] = None
        self._mps: Optional[_LoadedMPS] = None
        self._sklearn: Optional[_LoadedSKLearn] = None
        self._available = False
        self._cache: Dict[tuple, float] = {}
        self._load()

    @property
    def available(self) -> bool:
        return self._available

    @property
    def backend(self) -> str:
        if self.model_type == "mps_nn":
            return "pytorch-mps"
        if self.model_type == "sklearn":
            return "sklearn-gbm"
        return "lightgbm"

    def _load(self) -> None:
        try:
            if self.model_type == "mps_nn":
                self._load_mps()
            elif self.model_type == "sklearn":
                self._load_sklearn()
            else:
                self._load_lgbm()
            self._available = True
            return
        except Exception as exc:
            # BP-1: log the failure reason — silent pass hides real problems
            import logging as _log
            _log.getLogger(__name__).warning(
                "[traffic_ml] Primary model load failed (%s): %s", self.model_type, exc
            )

        # LightGBM failed → try sklearn GBM first (pure Python, no torch dependency)
        if self.model_type not in ("mps_nn", "sklearn"):
            try:
                self._load_sklearn()
                self.model_type = "sklearn"
                self._available = True
                import logging as _log
                _log.getLogger(__name__).info(
                    "[traffic_ml] LightGBM unavailable; switched to scikit-learn GBM backend."
                )
                return
            except Exception as exc2:
                import logging as _log
                _log.getLogger(__name__).warning("[traffic_ml] sklearn load failed: %s", exc2)

        # sklearn also failed → try PyTorch MLP
        if self.model_type not in ("mps_nn", "sklearn"):
            try:
                self._load_mps()
                self.model_type = "mps_nn"
                self._available = True
                import logging as _log
                _log.getLogger(__name__).info("[traffic_ml] Switched to PyTorch MLP backend.")
                return
            except Exception as exc3:
                import logging as _log
                _log.getLogger(__name__).warning("[traffic_ml] MPS/PyTorch load failed: %s", exc3)

        self._available = False
        import logging as _log
        _log.getLogger(__name__).warning(
            "[traffic_ml] No ML model available — using heuristic fallback."
        )




    def _load_lgbm(self) -> None:
        if lgb is None:
            raise ImportError("lightgbm not installed")
        bundle = joblib.load(os.path.join(self.models_dir, "traffic_lgbm.pkl"))

        self._lgbm = _LoadedLGBM(
            model=bundle["model"],
            encoders=bundle["encoders"],
            feature_cols=bundle["feature_cols"],
            categorical=bundle["categorical"],
            numeric=bundle["numeric"],
        )

    def _load_sklearn(self) -> None:
        bundle = joblib.load(os.path.join(self.models_dir, "traffic_sklearn.pkl"))
        self._sklearn = _LoadedSKLearn(
            model=bundle["model"],
            encoders=bundle["encoders"],
            feature_cols=bundle["feature_cols"],
            categorical=bundle["categorical"],
            numeric=bundle["numeric"],
        )

    def _load_mps(self) -> None:
        import torch
        import torch.nn as nn

        # Ensure sklearn is available for joblib to unpickle StandardScalers
        if StandardScaler is None:
            raise ImportError("scikit-learn required to load MPS preprocessing")

        state = torch.load(os.path.join(self.models_dir, "traffic_mps.pt"), map_location="cpu", weights_only=True)
        preproc = joblib.load(os.path.join(self.models_dir, "traffic_mps_preproc.pkl"))

        in_dim = state["in_dim"]

        class TTIMlp(nn.Module):
            def __init__(self, in_dim_: int):
                super().__init__()
                self.net = nn.Sequential(
                    nn.Linear(in_dim_, 128),
                    nn.ReLU(),
                    nn.Dropout(0.1),
                    nn.Linear(128, 64),
                    nn.ReLU(),
                    nn.Linear(64, 1),
                )

            def forward(self, x):
                return self.net(x)

        if torch.backends.mps.is_available():
            device = torch.device("mps")
        elif torch.cuda.is_available():
            device = torch.device("cuda")
        else:
            device = torch.device("cpu")

        m = TTIMlp(in_dim).to(device)
        m.load_state_dict(state["state_dict"])
        m.eval()

        self._mps = _LoadedMPS(
            torch_model=m,
            encoders=preproc["encoders"],
            scaler_cat=preproc["scaler_cat"],
            scaler_num=preproc["scaler_num"],
            categorical=preproc["categorical"],
            numeric=preproc["numeric"],
            device=device,
        )

    # ---- Feature construction helpers ----

    def _encode_cat(self, encoder, value: str, fallback: str) -> int:
        classes = list(encoder.classes_)
        if value not in classes:
            value = fallback if fallback in classes else classes[0]
        return int(encoder.transform([value])[0])

    def _build_row(
        self,
        bundle_encoders: Dict[str, Any],
        categorical: List[str],
        area: str,
        weather: str,
        road: Optional[str],
    ) -> Dict[str, int]:
        """
        Encode the categorical half of the feature row.
        Road is optional — when unknown, pick the most common road for the area
        (we approximate with the first class the encoder learned).
        """
        out: Dict[str, int] = {}
        for col in categorical:
            enc = bundle_encoders[col]
            if col == "Area Name":
                out[col + "_enc"] = self._encode_cat(enc, area, KNOWN_AREAS[0])
            elif col == "Road/Intersection Name":
                fallback = list(enc.classes_)[0]
                out[col + "_enc"] = self._encode_cat(enc, road or fallback, fallback)
            elif col == "Weather Conditions":
                out[col + "_enc"] = self._encode_cat(enc, weather, "Clear")
            else:
                out[col + "_enc"] = 0
        return out

    # ---- Public prediction ----

    def predict_tti(
        self,
        area: str,
        weather: str,
        day_of_week: int,
        month: int,
        road: Optional[str] = None,
        roadwork_flag: int = 0,
    ) -> Optional[float]:
        """
        Returns the predicted Travel Time Index (~1.0 to 1.5) for the
        given area/weather/day combo. Returns None if the model is not available.
        """
        if not self._available:
            return None

        # Cache key: keep road out since we always pass None from the public API.
        cache_key = (self.model_type, area, weather, int(day_of_week), int(month), int(roadwork_flag))
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        is_weekend = int(day_of_week >= 5)

        if self.model_type == "mps_nn" and self._mps is not None:
            cat_row = self._build_row(self._mps.encoders, self._mps.categorical, area, weather, road)
            cat_arr = np.array([[cat_row[c + "_enc"] for c in self._mps.categorical]], dtype=np.float32)
            num_arr = np.array([[day_of_week, month, is_weekend, roadwork_flag]], dtype=np.float32)
            cat_s = self._mps.scaler_cat.transform(cat_arr)
            num_s = self._mps.scaler_num.transform(num_arr)
            x = np.concatenate([cat_s, num_s], axis=1).astype(np.float32)

            import torch
            with torch.no_grad():
                t = torch.tensor(x, device=self._mps.device)
                pred = float(self._mps.torch_model(t).cpu().numpy().ravel()[0])
            
            # Clamp to plausible TTI range
            pred = max(1.0, min(pred, 2.5))
            self._cache[cache_key] = pred
            return pred

        if self._lgbm is not None:
            cat_row = self._build_row(self._lgbm.encoders, self._lgbm.categorical, area, weather, road)
            feat_vals = [cat_row[c + "_enc"] for c in self._lgbm.categorical] + [day_of_week, month, is_weekend, roadwork_flag]
            X = pd.DataFrame([feat_vals], columns=self._lgbm.feature_cols)
            pred = float(self._lgbm.model.predict(X)[0])
            
            # Clamp to plausible TTI range
            pred = max(1.0, min(pred, 2.5))
            self._cache[cache_key] = pred
            return pred

        if self._sklearn is not None:
            cat_row = self._build_row(self._sklearn.encoders, self._sklearn.categorical, area, weather, road)
            feat_vals = [cat_row[c + "_enc"] for c in self._sklearn.categorical] + [day_of_week, month, is_weekend, roadwork_flag]
            import pandas as pd
            X = pd.DataFrame([feat_vals], columns=self._sklearn.feature_cols)
            # Use .values to avoid "X has feature names" warning
            pred = float(self._sklearn.model.predict(X.values)[0])
            # Clamp to plausible TTI range
            pred = max(1.0, min(pred, 2.5))
            self._cache[cache_key] = pred
            return pred

        return None

    def multiplier_for_segment(
        self,
        hour: int,
        source: Optional[str],
        destination: Optional[str],
        weather: str,
        day_of_week: Optional[int] = None,
        month: Optional[int] = None,
    ) -> Optional[Tuple[float, str]]:
        """
        High-level entry point used by traffic_model.py.
        Returns (ml_tti, matched_area) or None if no area could be detected.
        The caller composes this with hour-of-day and mode sensitivity.
        """
        area = detect_area(source) or detect_area(destination)
        if area is None:
            return None

        from datetime import datetime
        now = datetime.now()
        dow = day_of_week if day_of_week is not None else now.weekday()
        mo = month if month is not None else now.month

        tti = self.predict_tti(
            area=area,
            weather=weather or "Clear",
            day_of_week=dow,
            month=mo,
            road=None,        # road name not available at this call site
            roadwork_flag=0,  # roadwork data not available at this call site
        )
        if tti is None:
            return None
        return tti, area


# ----------------------------------------------------------------------------
# Singleton for the running Flask app. Lazy-loaded so importing this module
# at startup never blocks — if no model is on disk we simply disable ML.
# ----------------------------------------------------------------------------

_PREDICTOR: Optional[TrafficPredictor] = None


def get_predictor(models_dir: Optional[str] = None) -> TrafficPredictor:
    """
    Lazy singleton. Model type is controlled by the env var TRAFFIC_MODEL_TYPE
    (values: "lightgbm" or "mps_nn"). Defaults to lightgbm.
    """
    global _PREDICTOR
    if _PREDICTOR is not None:
        return _PREDICTOR

    if models_dir is None:
        project_root = Path(__file__).resolve().parent.parent
        models_dir = str(project_root / "models")

    model_type = os.environ.get("TRAFFIC_MODEL_TYPE", "lightgbm").lower()
    _PREDICTOR = TrafficPredictor(models_dir=models_dir, model_type=model_type)
    return _PREDICTOR
