# 📡 API Reference

RouteCraft provides a RESTful API for routing, job status, and system monitoring.

## 📍 Routing Endpoints

### `POST /v1/route`
Calculates routes synchronously. Note: If the graph is not in the cache, this may take up to 25s.

**Request Body**
```json
{
  "source": "Koramangala",
  "destination": "Whitefield",
  "preference": "balanced",
  "weather": "Clear",
  "hour": 18
}
```

**Success Response (200 OK)**
```json
{
  "balanced": {
    "total_time": 65,
    "total_cost": 450,
    "eta_p10": 58,
    "eta_p50": 65,
    "eta_p90": 75,
    "segments": [...]
  },
  "fastest": {...},
  "cheapest": {...},
  "surge": {
    "multiplier": 1.5,
    "label": "Moderate Surge"
  },
  "ml": {
    "backend": "lightgbm",
    "used": true
  }
}
```

### `POST /v1/route/async`
Starts a background routing job and returns a job ID. Preferred for cold-start scenarios.

**Success Response (202 Accepted)**
```json
{
  "job_id": "8f3a-2b1c...",
  "poll_url": "/v1/jobs/8f3a-2b1c..."
}
```

---

## ⏱️ Job Management

### `GET /v1/jobs/<job_id>`
Checks the status of an asynchronous routing request.

**Response (Pending)**
```json
{ "status": "pending" }
```

**Response (Done)**
```json
{
  "status": "done",
  "result": { ... route data ... }
}
```

---

## 🏥 Health & Metrics

### `GET /health`
Returns system status, including ML backend availability and cache tier.

### `GET /metrics`
Returns Prometheus-style metrics:
- `total_requests`: Total routing calls.
- `cache_hits`: Number of requests served from RAM/DiskCache.
- `avg_latency_ms`: Rolling average of response times.

---

## 🔗 Deep Links

RouteCraft supports direct handoff to external booking platforms:

- **Uber**: `/book/uber?source=...&destination=...`
- **Metro**: `/book/metro?source=...&destination=...` (Opens Google Maps Transit)
- **BMTC**: `/book/bmtc?source=...&destination=...` (Opens Google Maps Bus)
