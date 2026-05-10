"""
RouteCraft — Airflow DAG: Cache Warmer
======================================
Runs every 30 minutes. Pre-builds the transit graph for all upcoming
traffic periods + current weather so Flask never serves a cold build.

Schedule:  Every 30 minutes
Tasks:
  1. fetch_weather       → Get current Bangalore weather condition
  2. warm_peak_graphs    → Build graphs for the next 3 traffic buckets
  3. warm_rainy_graphs   → If raining, pre-build rain variants too
  4. validate_cache      → Confirm all expected keys are present
  5. notify_flask        → Hit /internal/cache-ready so Flask knows

Architecture:
  Airflow worker writes to a shared DiskCache directory.
  Flask reads from the same DiskCache directory on every request.
  Both processes share state via filesystem — no Redis required.
"""

from __future__ import annotations

import os
import sys
import json
import logging
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.utils.dates import days_ago

# ---------------------------------------------------------------------------
# DAG default args
# ---------------------------------------------------------------------------
DEFAULT_ARGS = {
    "owner": "routecraft",
    "depends_on_past": False,
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=2),
}

# ---------------------------------------------------------------------------
# Shared config — must match CACHE_DIR used in cache_backend.py
# ---------------------------------------------------------------------------
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR    = os.path.join(PROJECT_ROOT, ".graph_cache")
WEATHER_FILE = os.path.join(PROJECT_ROOT, ".current_weather.json")

# Hour buckets that the Flask app uses (must stay in sync with app.py)
TRAFFIC_BUCKETS = [0, 6, 8, 12, 17, 23]

# Weather conditions to pre-warm (prioritised by frequency in Bangalore)
ALWAYS_WARM = ["Clear", "Light Rain"]
RAINY_EXTRA = ["Rain", "Heavy Rain"]

# ---------------------------------------------------------------------------
# Task 1: Fetch current Bangalore weather
# ---------------------------------------------------------------------------
def fetch_weather(**context) -> str:
    """
    Fetch current weather for Bangalore.
    Uses Open-Meteo (free, no API key needed).
    Falls back to 'Clear' if unreachable.
    """
    import urllib.request
    import json

    BANGALORE_LAT = 12.9716
    BANGALORE_LON = 77.5946
    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={BANGALORE_LAT}&longitude={BANGALORE_LON}"
        f"&current_weather=true"
    )
    weather = "Clear"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read())
            code = data.get("current_weather", {}).get("weathercode", 0)
            # WMO weather code mapping to RouteCraft weather strings
            if code in (61, 63, 80, 81):
                weather = "Light Rain"
            elif code in (65, 82):
                weather = "Rain"
            elif code in (67, 83, 84):
                weather = "Heavy Rain"
            else:
                weather = "Clear"
    except Exception as e:
        logging.warning(f"[airflow:fetch_weather] API failed ({e}), using Clear")

    # Persist for downstream tasks
    os.makedirs(os.path.dirname(WEATHER_FILE), exist_ok=True)
    with open(WEATHER_FILE, "w") as f:
        json.dump({"weather": weather, "fetched_at": datetime.utcnow().isoformat()}, f)

    logging.info(f"[airflow:fetch_weather] Current Bangalore weather: {weather}")
    context["ti"].xcom_push(key="current_weather", value=weather)
    return weather


# ---------------------------------------------------------------------------
# Task 2: Warm graphs for peak buckets × base weather conditions
# ---------------------------------------------------------------------------
def warm_peak_graphs(**context) -> dict:
    """
    Pre-build graphs for all traffic buckets × ALWAYS_WARM weathers.
    This covers 99% of user requests under normal conditions.
    """
    sys.path.insert(0, PROJECT_ROOT)
    from graph_builder import MultiLayerGraphBuilder
    from data_loader import DataLoader
    from disk_cache import DiskCache

    cache = DiskCache(CACHE_DIR)
    data_loader = DataLoader(base_dir=PROJECT_ROOT)
    locations = data_loader.load_locations()

    results = {"built": [], "skipped": []}
    current_hour = datetime.now().hour

    # Determine which buckets are upcoming (next 6 hours)
    upcoming = [b for b in TRAFFIC_BUCKETS if b >= _bucket_hour(current_hour)]
    if not upcoming:
        upcoming = TRAFFIC_BUCKETS  # wrap around at midnight

    for weather in ALWAYS_WARM:
        for bucket in upcoming:
            cache_key = f"{bucket}:{weather}:lightgbm"
            if cache.get(cache_key) is not None:
                results["skipped"].append(cache_key)
                logging.info(f"[airflow:warm_peak] Cache HIT — skipping {cache_key}")
                continue

            logging.info(f"[airflow:warm_peak] Building graph for {cache_key} ...")
            try:
                builder = MultiLayerGraphBuilder(locations, base_dir=PROJECT_ROOT)
                graph   = builder.build_graph(hour=bucket, weather=weather)
                cache.set(cache_key, (graph, {}), ttl_seconds=3600)
                results["built"].append(cache_key)
                logging.info(f"[airflow:warm_peak] Cached {cache_key}")
            except Exception as e:
                logging.error(f"[airflow:warm_peak] FAILED {cache_key}: {e}")

    return results


# ---------------------------------------------------------------------------
# Task 3: Warm rainy variants if it's currently raining
# ---------------------------------------------------------------------------
def warm_rainy_graphs(**context) -> dict:
    """
    Only executed when current weather is rainy (avoids wasted compute).
    Pre-builds Rain + Heavy Rain variants for peak hours.
    """
    current_weather = context["ti"].xcom_pull(
        task_ids="fetch_weather", key="current_weather"
    ) or "Clear"

    if current_weather not in ("Light Rain", "Rain", "Heavy Rain"):
        logging.info("[airflow:warm_rainy] Not raining — skipping rainy graph builds")
        return {"skipped": True}

    sys.path.insert(0, PROJECT_ROOT)
    from graph_builder import MultiLayerGraphBuilder
    from data_loader import DataLoader
    from disk_cache import DiskCache

    cache = DiskCache(CACHE_DIR)
    data_loader = DataLoader(base_dir=PROJECT_ROOT)
    locations = data_loader.load_locations()

    results = {"built": []}
    for weather in RAINY_EXTRA:
        for bucket in [8, 17]:   # morning + evening peak only
            cache_key = f"{bucket}:{weather}:lightgbm"
            if cache.get(cache_key) is not None:
                continue
            try:
                builder = MultiLayerGraphBuilder(locations, base_dir=PROJECT_ROOT)
                graph   = builder.build_graph(hour=bucket, weather=weather)
                cache.set(cache_key, (graph, {}), ttl_seconds=1800)
                results["built"].append(cache_key)
            except Exception as e:
                logging.error(f"[airflow:warm_rainy] FAILED {cache_key}: {e}")

    return results


# ---------------------------------------------------------------------------
# Task 4: Validate cache completeness
# ---------------------------------------------------------------------------
def validate_cache(**context) -> dict:
    """
    Check that the most critical cache keys are present.
    Raises on any missing key so Airflow shows the DAG run as failed.
    """
    sys.path.insert(0, PROJECT_ROOT)
    from disk_cache import DiskCache

    cache = DiskCache(CACHE_DIR)
    required_keys = [f"{b}:Clear:lightgbm" for b in [8, 17]]
    missing = [k for k in required_keys if cache.get(k) is None]

    if missing:
        raise ValueError(f"[airflow:validate] Missing cache keys: {missing}")

    stats = cache.stats()
    logging.info(f"[airflow:validate] Cache healthy — {stats['total_keys']} keys, "
                 f"{stats['total_size_mb']:.1f} MB")
    return stats


# ---------------------------------------------------------------------------
# Task 5: Notify Flask server that cache is ready
# ---------------------------------------------------------------------------
def notify_flask(**context) -> None:
    """
    Ping the internal Flask health/cache endpoint so the app
    can refresh its in-memory reference to the disk cache.
    Fails silently — Flask is optional (may not be running).
    """
    import urllib.request
    port = os.environ.get("PORT", "5000")
    url  = f"http://127.0.0.1:{port}/internal/cache-refreshed"
    try:
        with urllib.request.urlopen(url, timeout=3) as resp:
            logging.info(f"[airflow:notify] Flask notified — {resp.status}")
    except Exception as e:
        logging.info(f"[airflow:notify] Flask not reachable ({e}) — OK if not running")


# ---------------------------------------------------------------------------
# Helper: must match _bucket_hour() in app.py exactly
# ---------------------------------------------------------------------------
def _bucket_hour(h: int) -> int:
    if h <= 5:  return 0
    if h <= 7:  return 6
    if h <= 11: return 8
    if h <= 15: return 12
    if h <= 22: return 17
    return 23


# ---------------------------------------------------------------------------
# DAG definition
# ---------------------------------------------------------------------------
with DAG(
    dag_id="routecraft_cache_warmer",
    description="Pre-warm RouteCraft transit graph cache every 30 minutes",
    default_args=DEFAULT_ARGS,
    schedule_interval="*/30 * * * *",   # every 30 minutes
    start_date=days_ago(1),
    catchup=False,
    max_active_runs=1,
    tags=["routecraft", "cache", "performance"],
) as dag:

    t1 = PythonOperator(
        task_id="fetch_weather",
        python_callable=fetch_weather,
        doc_md="Fetch current Bangalore weather from Open-Meteo (free, no key needed).",
    )

    t2 = PythonOperator(
        task_id="warm_peak_graphs",
        python_callable=warm_peak_graphs,
        doc_md="Build graphs for all traffic buckets × Clear and Light Rain weather.",
    )

    t3 = PythonOperator(
        task_id="warm_rainy_graphs",
        python_callable=warm_rainy_graphs,
        doc_md="Build Rain/Heavy Rain graphs only when it is currently raining.",
    )

    t4 = PythonOperator(
        task_id="validate_cache",
        python_callable=validate_cache,
        doc_md="Assert all critical cache keys are present. Fails DAG run if any missing.",
    )

    t5 = PythonOperator(
        task_id="notify_flask",
        python_callable=notify_flask,
        doc_md="Ping Flask /internal/cache-refreshed so it picks up new graphs.",
    )

    # Pipeline: fetch weather → warm both graph sets in parallel → validate → notify
    t1 >> [t2, t3] >> t4 >> t5
