# 🏗️ RouteCraft Architecture

RouteCraft is designed as a high-availability, low-latency transit intelligence system. It mirrors the architectural patterns used by industry leaders like Uber and Amazon to solve complex routing and ETA prediction problems.

## System Overview

The system is built on four core pillars:
1. **Multi-Modal Graph Engine**: A state-space graph where nodes represent `(location, mode)` pairs, allowing for realistic mode-switching logic.
2. **3-Stage ML Fallback**: A resilient inference chain that ensures traffic-aware ETAs even if hardware acceleration or primary models are unavailable.
3. **3-Tier Caching Strategy**: A tiered storage approach to balance the 25s cost of building a global graph against the microsecond requirement for user queries.
4. **Airflow Orchestration**: Automated background jobs for cache warming and ML lifecycle management.

---

## 🗺️ Multi-Modal Graph Engine

Unlike simple road-network graphs, RouteCraft uses a **State-Space Graph**.

### Nodes
Nodes are defined as a combination of a physical location and a transport mode:
- `(Koramangala, WALK)`
- `(Koramangala, CAB)`
- `(Indiranagar Station, METRO)`

### Edges
- **Intra-mode Edges**: Standard travel edges (e.g., Koramangala to HSR via Cab). Weights are calculated using haversine distance, the ML traffic model, and mode-specific speed constants.
- **Inter-mode (Transfer) Edges**: Fixed-penalty edges that allow switching modes (e.g., walking from a bus stop into a Metro station).

---

## ⚡ 3-Tier Caching Strategy

Building a graph with 300+ nodes and thousands of edges (including GTFS bus schedules) takes ~25 seconds. RouteCraft avoids this latency during user requests using a tiered cache:

| Tier | Component | Latency | Storage | Role |
|---|---|---|---|---|
| **Tier 1** | In-Process RAM | <1ms | Python Dict | Instant access for the most frequent queries. |
| **Tier 2** | DiskCache | 5-50ms | SQLite/Disk | Persistent pre-built graphs. Populated by the Airflow Cache Warmer. |
| **Tier 3** | Cold Build | ~25s | On-the-fly | The "Source of Truth". Only used if Tier 1 and 2 miss. |

---

## 🤖 ML Inference Lifecycle

The `TrafficPredictor` follows a "Graceful Degradation" pattern:

1. **LightGBM**: The primary high-performance model.
2. **Scikit-Learn GBM**: Fallback if LightGBM binaries are incompatible with the host OS.
3. **PyTorch MLP**: Experimental GPU-accelerated backend (MPS for Apple Silicon).
4. **Heuristic**: A sophisticated fallback based on historical traffic period constants (Peak, Off-peak, etc.).

---

## 🔄 Background Orchestration

RouteCraft is not just a Flask app; it's a "living" system managed by **Apache Airflow**:
- **Cache Warmer DAG**: Fetches live weather every 30 minutes and "warms up" Tier 2 graphs for the next expected traffic buckets.
- **ML Retrainer DAG**: Monitors model performance daily and atomically swaps model files if it detects data drift.
