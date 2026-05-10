# 🤖 ML Traffic Services

RouteCraft uses Machine Learning to transform static distances into dynamic, traffic-aware ETAs. The system is designed to handle model loading, inference, and lifecycle management without external dependencies like AWS SageMaker or Vertex AI.

## 📊 The Dataset

Models are trained on the **Bangalore Traffic Pulse** dataset (2022–2024), which includes:
- **Spatial Features**: Area Name, Road/Intersection Name.
- **Temporal Features**: Day of week, Month, Hour.
- **Environmental Features**: Weather (Rain, Fog, Clear), Roadwork/Construction flags.

**Target Variable**: Travel Time Index (TTI). A TTI of 1.5 means a trip takes 50% longer than it would in free-flow traffic.

---

## 🏗️ 3-Stage Predictor (`services/traffic_ml.py`)

The `TrafficPredictor` class is a resilient singleton that handles model loading across different backends.

### 1. LightGBM (Primary)
- **File**: `models/traffic_lgbm.pkl`
- **Why**: Fastest inference and best handling of categorical features (Area/Road).
- **Optimization**: Uses `joblib` for zero-copy serialization.

### 2. Scikit-Learn GBM (CPU Fallback)
- **File**: `models/traffic_sklearn.pkl`
- **Why**: Pure Python/C++ implementation with no complex DLL dependencies. Ensures the system works on standard Windows/Linux servers.

### 3. PyTorch MLP (Experimental)
- **File**: `models/traffic_mps.pt`
- **Why**: Demonstrates GPU acceleration. Optimized for Apple Silicon (MPS) but falls back to CPU.

### 4. Heuristic Fallback
If no model files are found, the system uses a `multiplier_for_segment` logic defined in `traffic_model.py`:
- **Peak Hour**: 1.8x multiplier.
- **Rainy Weather**: +0.3 boost.
- **Construction**: +0.2 boost.

---

## 📈 MLOps: Drift & Retraining

RouteCraft implements a professional MLOps loop using **Evidently AI** and **Airflow**:

1. **Drift Detection**: The `drift_monitor.py` compares fresh traffic data against the training distribution.
2. **Automated Retraining**: If a "Data Drift" alert is triggered, the `ml_retrainer_dag` triggers `train_sklearn_model.py`.
3. **Atomic Swap**: New models are validated against an RMSE threshold. If they pass, they are moved into `models/` using `os.replace()`, ensuring the Flask server never sees a partially written file.

---

## 🛠️ Training the Models

You can regenerate the models at any time:

```bash
# Standard training
python train_traffic_model.py

# Light-weight sklearn-only training
python train_sklearn_model.py
```

*Note: Model binaries (`.pkl`, `.pt`) are excluded from Git to keep the repository size manageable. Run the training scripts after cloning to enable ML features.*
