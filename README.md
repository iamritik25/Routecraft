<div align="center">

# ⚡ RouteCraft

### Production-Grade Multi-Modal Transit Intelligence for Bengaluru

*The same problems Uber and Amazon solve at scale — ETA prediction, multi-modal routing, ML-powered traffic modelling, surge pricing, async jobs, and real-time cache orchestration — built end-to-end from scratch.*

[![Python](https://img.shields.io/badge/Python-3.12+-3776ab?logo=python&logoColor=white&style=for-the-badge)](https://python.org)
[![Flask](https://img.shields.io/badge/Flask-3.x-000000?logo=flask&logoColor=white&style=for-the-badge)](https://flask.palletsprojects.com)
[![Airflow](https://img.shields.io/badge/Apache_Airflow-2.8+-017CEE?logo=apacheairflow&logoColor=white&style=for-the-badge)](https://airflow.apache.org)
[![LightGBM](https://img.shields.io/badge/LightGBM-ML_Backend-2c8000?style=for-the-badge)](https://lightgbm.readthedocs.io)
[![License](https://img.shields.io/badge/License-MIT-blue?style=for-the-badge)](LICENSE)

<br/>

> **Walk · Auto · Cab · BMTC Bus · Namma Metro**
> Ranked by cost, time, or a Pareto-optimal balance — with real ML-backed traffic prediction, live surge pricing, and ETA confidence intervals.

<br/>

| ⚡ 56ms warm query | 🔴 Surge Pricing | 📊 P10/P50/P90 ETA | 🤖 3-Stage ML | 🗺️ 7 Route Variants |
|:---:|:---:|:---:|:---:|:---:|

</div>

---

## 🎯 Why This Project Matters

| Industry Challenge | Uber / Amazon Solution | RouteCraft Implementation |
|---|---|---|
| Multi-modal routing | State-space graph engine | Custom Dijkstra on `(location, mode)` nodes |
| ETA prediction | DeepETA / ML models | LightGBM → sklearn-GBM → PyTorch MLP fallback chain |
| Graceful degradation | Circuit breakers | 3-stage ML fallback, heuristic always active |
| Surge pricing | Supply/demand multiplier | Real-time 1.0x–3.5x multiplier engine |
| Cold-start performance | Pre-computed graphs | 3-tier cache: RAM → DiskCache → cold build |
| Cache orchestration | Airflow DAGs | `cache_warmer_dag.py` runs every 30 min |
| ML model drift | MLflow + Evidently | Daily drift check + zero-downtime model swap |
| A/B Testing | Feature flag routing | Deterministic hash-based backend allocator |
| Async processing | 202 Accepted pattern | `JobStore` + polling endpoint |
| Observability | Structured logging + metrics | JSON logs, `/health`, `/metrics` endpoints |

---

## 🏗️ System Architecture

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                        CLIENT (Browser)                                      │
│   Leaflet Map · Route Tabs · Surge Banner · ETA Confidence Band · ML Badge  │
└─────────────────────────────┬────────────────────────────────────────────────┘
                              │  POST /v1/route  |  GET /v1/route/async
                              ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                      Flask Application  (app.py)                             │
│                                                                              │
│  ┌─────────────────┐  ┌──────────────────┐  ┌──────────────────────────┐   │
│  │  PlaceResolver  │  │  SurgePricing    │  │  A/B Testing             │   │
│  │  4-strategy     │  │  Engine          │  │  lightgbm ↔ sklearn-gbm  │   │
│  │  + Nominatim    │  │  1.0x – 3.5x     │  │  sticky session hash     │   │
│  └─────────────────┘  └──────────────────┘  └──────────────────────────┘   │
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                  3-Tier Graph Cache                                  │   │
│  │  Tier 1: In-process dict   (microseconds, RAM)                       │   │
│  │  Tier 2: DiskCache         (milliseconds, pre-built by Airflow DAG)  │   │
│  │  Tier 3: Cold build        (~25s, GTFS + ML + haversine)             │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│  Endpoints: /v1/route  /v1/route/async  /v1/jobs/<id>                       │
│             /health    /metrics         /internal/cache-refreshed            │
│             /book/uber /book/metro      /book/bmtc                           │
└─────────────────────────────┬────────────────────────────────────────────────┘
                              │ cache miss → build
                              ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                  MultiLayerGraphBuilder  (graph_builder.py)                  │
│                                                                              │
│  Nodes : (location, mode) pairs — 69 hubs × 5 modes = 345 nodes             │
│  Edges : walk/auto/cab  ← haversine + time_engine + cost_engine             │
│          bus            ← BMTC GTFS stop_times  (4,433 stops, 4,271 routes) │
│          metro          ← Purple + Green line KML (63 stations)             │
│          mode-switch    ← fixed penalty at hubs/stations                    │
│                                                                              │
│  Performance optimisations:                                                  │
│  • GTFS CSV read ONCE per process (module-level cache)                       │
│  • 305,877 haversine calls computed ONCE (proximity cache)                  │
│  • Hour bucketing: 24h → 5 traffic periods (more cache hits)                │
└─────────────────────────────┬────────────────────────────────────────────────┘
                              │ per-edge weight
                              ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│               3-Stage ML Fallback  (services/traffic_ml.py)                  │
│                                                                              │
│   Stage 1 → LightGBM        (traffic_lgbm.pkl)  fastest, default            │
│   Stage 2 → sklearn GBM     (traffic_sklearn.pkl) if LightGBM missing       │
│   Stage 3 → PyTorch MLP     (traffic_mps.pt)    GPU, if torch available     │
│   Fallback → Heuristic      hour-of-day × mode sensitivity × zone penalty   │
│                                                                              │
│   Prediction cache: O(1) for ~6,720 unique (area, weather, day, month)      │
└─────────────────────────────┬────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                   RouteEngine  (route_engine.py)                             │
│                                                                              │
│   7 Dijkstra runs → cheapest · fastest · balanced · cab_only                │
│                       metro_only · metro+cab · bus_only                      │
│   ETA Confidence Intervals: P10 / P50 / P90 on every route                  │
└──────────────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│               Apache Airflow Orchestration  (dags/)                          │
│                                                                              │
│   cache_warmer_dag    → every 30 min                                         │
│     fetch_weather (Open-Meteo, free)                                         │
│     warm_peak_graphs  → builds Clear + Light Rain graphs for next buckets   │
│     warm_rainy_graphs → builds Rain/Heavy Rain graphs when raining          │
│     validate_cache    → asserts all critical keys present                    │
│     notify_flask      → POST /internal/cache-refreshed                      │
│                                                                              │
│   ml_retrainer_dag    → daily at 2 AM                                        │
│     check_drift       → Evidently drift detection                            │
│     retrain_model     → sklearn GBM retrain if drift detected               │
│     validate_model    → RMSE threshold gate (protects production)            │
│     swap_model        → atomic os.replace() zero-downtime swap              │
│     invalidate_cache  → clears stale graphs for fresh rebuild               │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## 🚀 Quick Start (3 Steps)

### Step 1 — Setup (run once)

```bat
setup.bat
```

This creates `.venv\` inside the project folder, installs all packages **locally** (nothing global), and copies `.env.example` → `.env`.

> ✅ Delete the project folder = delete every package. Nothing left on your PC.

### Step 2 — Run the server

```bat
run.bat
```

Opens at → **http://127.0.0.1:5000**

### Step 3 (Optional) — Run the cache warmer alongside it

In a second terminal:

```bat
.venv\Scripts\python cache_warmer.py --interval 30
```

This pre-builds graphs every 30 minutes so users never wait for a cold build.

---

## 📦 Installation (Manual / Detailed)

### Requirements

- Python **3.10+** (3.12 recommended)
- Windows / macOS / Linux
- No paid services, no API keys

### Install

```bash
# 1. Clone the repo
git clone https://github.com/iamritik25/routecraft.git
cd routecraft

# 2. Create local virtual environment
python -m venv .venv

# 3. Activate it
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS/Linux

# 4. Install dependencies
pip install -r requirements.txt

# 5. Copy env config
copy .env.example .env          # Windows
# cp .env.example .env          # macOS/Linux

# 6. Run
python app.py
# → http://127.0.0.1:5000
```

### (Optional) Train the ML model yourself

```bash
# Download dataset from Kaggle first (needs ~/.kaggle/kaggle.json)
kaggle datasets download -d preethamgouda/banglore-city-traffic-dataset -p data/ --unzip

# Train
python train_sklearn_model.py
# → models/traffic_sklearn.pkl
```

### (Optional) Run with full Apache Airflow

```bat
airflow_setup.bat       # installs Airflow inside .venv (one-time, ~5 min)

# Then in two separate terminals:
run.bat                 # Terminal 1 — Flask server
airflow_start.bat       # Terminal 2 — Airflow scheduler + UI

# Airflow UI → http://127.0.0.1:8080  (login: admin / admin)
```

---

## ⚙️ Configuration (.env)

All settings live in `.env` — never committed to Git.

```env
SECRET_KEY=<auto-generated 64-char hex>   # Flask session signing key
FLASK_ENV=development
PORT=5000

TRAFFIC_MODEL_TYPE=sklearn   # lightgbm | sklearn | mps_nn
MPS_TRAFFIC_PERCENT=10       # % of traffic sent to experimental backend

REDIS_URL=                   # leave blank → in-process cache (default)
GEOCODER_USER_AGENT=routecraft-yourname-2026
```

---

## 📡 API Reference

### `POST /v1/route` — Synchronous route calculation

```json
{
  "source":      "Koramangala",
  "destination": "Whitefield",
  "preference":  "balanced",
  "weather":     "Rain",
  "hour":        18
}
```

**Response:**

```json
{
  "balanced":  { "total_time": 66, "total_cost": 72, "eta_p10": 60, "eta_p50": 66, "eta_p90": 72 },
  "fastest":   { "total_time": 48, "total_cost": 530, "eta_confidence": "high" },
  "cheapest":  { ... },
  "cab_only":  { ... },
  "bus_only":  { ... },
  "surge":     { "multiplier": 2.0, "label": "🟠 High Surge" },
  "ml":        { "backend": "sklearn-gbm", "used": true, "hits": 3436 },
  "preferred": "balanced",
  "elapsed_ms": 56
}
```

### `POST /v1/route/async` — Non-blocking (202 Accepted)

```bash
POST /v1/route/async   → { "job_id": "abc123", "poll_url": "/v1/jobs/abc123" }
GET  /v1/jobs/abc123   → { "status": "done", "result": { ... } }
```

### Observability

```bash
GET /health    → { "status": "healthy", "cache_backend": "local", "ml_backend": "sklearn-gbm" }
GET /metrics   → { "total_requests": 17, "cache_hits": 12, "avg_response_ms": 56, "ml_hit_rate": 0.735 }
```

### Booking Deep Links

```bash
GET /book/uber?source=Koramangala&destination=Whitefield   → Uber app with pre-filled pickup/dropoff
GET /book/metro?source=MG Road&destination=Whitefield      → Google Maps Transit
GET /book/bmtc?source=Silk Board&destination=BTM Layout    → Google Maps Bus
```

---

## 🧠 Features In Detail

### 1. Multi-Modal Routing
- **5 transport modes:** Walk, Auto, Cab, BMTC Bus, Namma Metro
- **State-space graph:** nodes are `(location, mode)` tuples — enforces that you can only board metro at metro stations
- **7 route variants per query:** cheapest, fastest, balanced, cab-only, metro-only, metro+cab, bus-only
- **Pareto-optimal balanced route:** normalised cost + time so ₹200 doesn't dominate 45 minutes

### 2. ML Traffic Prediction — 3-Stage Fallback Chain
```
LightGBM (traffic_lgbm.pkl)
    ↓ missing?
sklearn GBM (traffic_sklearn.pkl)    ← default in this environment
    ↓ missing?
PyTorch MLP (traffic_mps.pt)
    ↓ unavailable?
Heuristic (hour-of-day × mode sensitivity)   ← always active
```
- Trained on **8,936 real Bengaluru traffic observations**
- **17.9% MAE improvement** over baseline
- **Prediction cache:** O(1) lookup for ~6,720 unique combos after warmup

### 3. ETA Confidence Intervals (P10 / P50 / P90)
Every route response includes statistical bounds:
- `eta_p10` — best case (light traffic)
- `eta_p50` — median expected time
- `eta_p90` — worst case (heavy congestion)
- `eta_confidence` — `high / medium / low` based on traffic variance

### 4. Surge Pricing Engine
- Real-time **1.0x – 3.5x** multiplier based on hour, weather, and demand area
- Labels: 🟢 Normal · 🟡 Moderate · 🟠 High · 🔴 Very High Surge
- Displayed as a live banner in the UI

### 5. 3-Tier Graph Cache
| Tier | Storage | Latency | Who Writes |
|---|---|---|---|
| Tier 1 | In-process RAM | ~0 ms | Flask (on build) |
| Tier 2 | DiskCache (`.graph_cache/`) | ~5–50 ms | Airflow DAG |
| Tier 3 | Cold build | ~25 s | Flask (fallback) |

### 6. Apache Airflow Orchestration
- **`cache_warmer_dag`** — runs every 30 min, fetches live Bangalore weather from Open-Meteo (free), pre-builds graphs for all upcoming traffic periods
- **`ml_retrainer_dag`** — runs daily at 2AM, checks data drift, retrains model if drift detected, validates RMSE, atomically swaps model file (zero downtime)
- **`cache_warmer.py`** — lightweight standalone alternative using `schedule` library (no Airflow needed for dev)

### 7. A/B Testing Framework
- Deterministic session hash → sticky backend assignment
- `TRAFFIC_MODEL_TYPE` env var for hard overrides
- Thread-safe counters exposed via `/metrics`

### 8. Async Job System (202 Accepted)
- `POST /v1/route/async` returns immediately with a `job_id`
- Background thread computes the route
- `GET /v1/jobs/<job_id>` polls for result
- Prevents browser timeouts on cold graph builds

### 9. Structured Observability
- All logs are **JSON-structured** (timestamp, level, module, message, fields)
- `/health` for infrastructure monitoring (load balancer probes)
- `/metrics` for Prometheus-style scraping
- `/internal/cache-refreshed` for Airflow ↔ Flask coordination

### 10. BMTC GTFS Integration
- **4,433 stops · 4,271 routes · 15,170 trips** parsed from real GTFS feed
- Proximity-based stop mapping: exact name match → 1.5km haversine fallback
- Module-level cache: 305,877 haversine calls computed **once per process**

---

## 📊 ML Results

Trained on **8,936 real Bengaluru traffic observations** (Kaggle dataset, Jan 2022 – Aug 2024).

| Metric | Baseline | LightGBM | sklearn GBM | PyTorch MLP |
|---|---|---|---|---|
| **Test MAE** | 0.1457 | 0.1208 | 0.1221 | **0.1196** |
| **Improvement** | — | −17.1% | −16.2% | **−17.9%** |
| **Test R²** | — | 0.140 | 0.128 | 0.159 |

Feature importance: `month > day_of_week > Road > Weather > Area > roadwork > is_weekend`

---

## ⚡ Performance

| Operation | Latency |
|---|---|
| Warm request (Tier 1 in-process cache hit) | **~30–100 ms** |
| Warm request (Tier 2 Airflow DiskCache hit) | **~50–200 ms** |
| Cold graph build (first time for new hour/weather) | ~25 s |
| Background pre-warm at startup | begins at server start |
| Airflow cache refresh cycle | every 30 minutes |
| 42 unit tests | **0.26 s** |

---

## 🧪 Tests

```bash
# Run all 42 tests
python -m pytest

# With coverage report
python -m pytest --cov .

# Specific file
python -m pytest tests/test_ab_testing.py -v
```

| Test File | Tests | What It Covers |
|---|---|---|
| `test_ab_testing.py` | 6 | Sticky sessions, env override, count tracking |
| `test_cost_engine.py` | 8 | Fare model, surge, mode pricing |
| `test_dijkstra.py` | 8 | Route finding, Pareto variants, ETA |
| `test_eta_confidence.py` | 6 | P10/P50/P90 bounds, confidence levels |
| `test_job_store.py` | 7 | Async job lifecycle, thread safety |
| `test_surge_engine.py` | 7 | Surge multipliers, labels, bounds |
| **Total** | **42** | **All passing in 0.26s** ✅ |

---

## 📁 Project Structure

```
routecraft/
│
├── 🐍 Core Backend
│   ├── app.py                    # Flask server — all HTTP routes, 3-tier cache
│   ├── graph_builder.py          # MultiLayerGraphBuilder (GTFS + Metro + Walk)
│   ├── route_engine.py           # Dijkstra + ETA confidence intervals
│   ├── traffic_model.py          # Two-layer traffic model
│   ├── surge_engine.py           # Surge pricing (1.0x–3.5x)
│   ├── ab_testing.py             # A/B backend allocator (sticky sessions)
│   ├── cache_backend.py          # Redis / in-process cache
│   ├── disk_cache.py             # Shared DiskCache (Airflow ↔ Flask)
│   ├── job_store.py              # Async 202 Accepted job system
│   ├── logger.py                 # Structured JSON logging
│   ├── schemas.py                # Pydantic v2 request validators
│   └── drift_monitor.py          # ML drift detection (Evidently)
│
├── 🌐 Frontend
│   ├── templates/index.html      # Flask HTML template
│   ├── static/app.js             # Surge banner, ETA band, coloured polylines
│   └── static/styles.css        # Full CSS (glassmorphism, dark panels)
│
├── ⚙️ Services
│   ├── services/traffic_ml.py    # 3-stage ML fallback chain
│   ├── services/geocoder.py      # Nominatim + exponential backoff + cache
│   ├── services/eta_confidence.py# P10/P50/P90 calculator
│   ├── services/metro_graph_builder.py
│   └── services/place_resolver.py
│
├── 🔄 Airflow DAGs
│   ├── dags/cache_warmer_dag.py  # Pre-warm graphs every 30 min
│   └── dags/ml_retrainer_dag.py  # Daily drift check + zero-downtime retrain
│
├── 🧪 Tests (42 tests, 0.26s)
│   ├── tests/conftest.py
│   ├── tests/test_ab_testing.py
│   ├── tests/test_cost_engine.py
│   ├── tests/test_dijkstra.py
│   ├── tests/test_eta_confidence.py
│   ├── tests/test_job_store.py
│   └── tests/test_surge_engine.py
│
├── 📦 Data
│   ├── locations.json            # 69 Bengaluru hubs with lat/lon/flags
│   ├── data/bmtc_gtfs/           # Real BMTC GTFS (4433 stops, 4271 routes)
│   ├── data/metro/               # Namma Metro KML (63 stations)
│   └── data/Banglore_traffic_Dataset.csv
│
├── 🤖 Models (pre-trained)
│   ├── models/traffic_lgbm.pkl
│   ├── models/traffic_mps.pt
│   └── models/traffic_sklearn.pkl
│
├── 🔧 Config & Setup
│   ├── .env.example              # Config template (safe to commit)
│   ├── .env                      # Your local config (never committed)
│   ├── requirements.txt
│   ├── pytest.ini
│   ├── pyrightconfig.json        # VS Code Pylance path config
│   ├── conftest.py               # Root pytest path fixer
│   ├── setup.bat                 # One-click install to .venv
│   ├── run.bat                   # Start server
│   ├── train.bat                 # Train ML model
│   ├── airflow_setup.bat         # Install Airflow into .venv
│   ├── airflow_start.bat         # Start Airflow scheduler + UI
│   └── cache_warmer.py           # Standalone 30-min cache warmer
│
└── ❌ Never committed
    ├── .env                      # Secrets
    ├── .venv/                    # All packages (local only)
    ├── .graph_cache/             # Runtime DiskCache
    └── .airflow/                 # Airflow local DB
```

---

## 🚧 Known Limitations & Honest Trade-offs

| Limitation | Why | Production Fix |
|---|---|---|
| ML covers only 8 Bengaluru areas | Dataset boundary | Train on more data / expand alias table |
| Daily granularity TTI | Dataset is daily aggregated | Integrate GTFS-Realtime feed |
| Flask dev server | Dev convenience | Gunicorn + Nginx, env-gated debug |
| sqlite Airflow DB | Local dev only | PostgreSQL + Celery executor |
| No auth on API | Local demo | JWT / API-key middleware |

---

## 🔮 Future Work

- [ ] **GTFS-Realtime** — live bus positions and delays
- [ ] **Prometheus + Grafana** — connect `/metrics` to monitoring dashboard
- [ ] **Docker Compose** — Flask + Airflow + Redis in one `docker-compose up`
- [ ] **WebSocket live ETA** — push updated ETA as traffic changes
- [ ] **Per-hour ML model** — retrain when hourly data available
- [ ] **All-pairs pre-computation** for fixed `(hour, weather)` buckets

---

## 💡 Interview Talking Points

**For Uber / Routing Engineers:**
- Built the same `(location, mode)` state-space graph Uber uses — mode constraints enforced at graph level
- 3-tier cache mirrors production pattern: L1 (RAM) → L2 (Redis/DiskCache) → L3 (rebuild)
- Hour bucketing reduces unique cache keys from 144 → 30 — same trick as traffic period binning
- Booking handoff via Uber deep links — same pattern as partner integrations

**For Amazon / ML Engineers:**
- End-to-end MLOps: training → MLflow tracking → Evidently drift → atomic model swap
- 3-stage ML fallback: zero downtime regardless of which backend is available
- Airflow DAG orchestration — production-grade scheduling with task dependencies, retries, RMSE gates
- Pydantic v2 schema validation — same pattern as Amazon's API input validation

---

<div align="center">

Built with 🧠 ML · 🗺️ Real Transit Data · ⚡ Zero API Keys · 🔄 Airflow Orchestration

**[Subrat Kumar Behera](https://github.com/iamritik25)** · MIT License

</div>
