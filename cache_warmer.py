"""
RouteCraft — Lightweight Cache Warmer (no Airflow needed)
=========================================================
A standalone Python process that replicates Airflow DAG logic using
the `schedule` library. Run this alongside `run.bat` when you don't
have Airflow installed yet.

Usage:
    python cache_warmer.py          # runs forever
    python cache_warmer.py --once   # run immediately then exit (for testing)

This is the LOCAL DEV equivalent of the Airflow DAG. In production,
replace this with the real Airflow scheduler.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
import urllib.request
import json
from datetime import datetime

# ── Configure logging ──────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='{"time":"%(asctime)s","level":"%(levelname)s","msg":"%(message)s"}',
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
log = logging.getLogger("cache_warmer")

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR    = os.path.join(PROJECT_ROOT, ".graph_cache")
TRAFFIC_BUCKETS = [0, 6, 8, 12, 17, 23]


def _bucket_hour(h: int) -> int:
    if h <= 5:  return 0
    if h <= 7:  return 6
    if h <= 11: return 8
    if h <= 15: return 12
    if h <= 22: return 17
    return 23


def fetch_current_weather() -> str:
    """Fetch live Bangalore weather from Open-Meteo (free, no API key)."""
    url = (
        "https://api.open-meteo.com/v1/forecast"
        "?latitude=12.9716&longitude=77.5946&current_weather=true"
    )
    try:
        with urllib.request.urlopen(url, timeout=8) as resp:
            data = json.loads(resp.read())
            code = data.get("current_weather", {}).get("weathercode", 0)
            if code in (61, 63, 80, 81): return "Light Rain"
            if code in (65, 82):         return "Rain"
            if code in (67, 83, 84):     return "Heavy Rain"
            return "Clear"
    except Exception as e:
        log.warning(f"Weather API unavailable ({e}), defaulting to Clear")
        return "Clear"


def warm_cache_job() -> None:
    """
    Core cache-warming job. Mirrors the Airflow DAG tasks:
      1. Fetch weather
      2. Build graphs for upcoming traffic buckets
      3. Log stats
    """
    log.info("Cache warm job started")
    start = time.perf_counter()

    sys.path.insert(0, PROJECT_ROOT)
    from graph_builder import MultiLayerGraphBuilder
    from data_loader import DataLoader
    from disk_cache import DiskCache

    # Step 1: Get current weather
    current_weather = fetch_current_weather()
    log.info(f"Current Bangalore weather: {current_weather}")

    # Step 2: Determine which weather conditions to warm
    weathers_to_warm = ["Clear", "Light Rain"]
    if current_weather in ("Light Rain", "Rain", "Heavy Rain"):
        weathers_to_warm += ["Rain"]

    # Step 3: Build graphs
    cache = DiskCache(CACHE_DIR)
    data_loader = DataLoader(base_dir=PROJECT_ROOT)
    locations = data_loader.load_locations()

    current_hour = datetime.now().hour
    current_bucket = _bucket_hour(current_hour)
    # Prioritise current + next bucket
    upcoming = [b for b in TRAFFIC_BUCKETS if b >= current_bucket] or TRAFFIC_BUCKETS

    built = 0
    skipped = 0
    for weather in weathers_to_warm:
        for bucket in upcoming[:3]:   # top 3 upcoming buckets
            key = f"{bucket}:{weather}:lightgbm"
            if cache.get(key) is not None:
                skipped += 1
                continue
            try:
                log.info(f"Building graph: {key}")
                builder = MultiLayerGraphBuilder(locations, base_dir=PROJECT_ROOT)
                graph   = builder.build_graph(hour=bucket, weather=weather)
                cache.set(key, (graph, {}), ttl_seconds=3600)
                built += 1
                log.info(f"Cached: {key}")
            except Exception as e:
                log.error(f"Failed to build {key}: {e}")

    elapsed = time.perf_counter() - start
    stats   = cache.stats()
    log.info(
        f"Cache warm complete — built={built}, skipped={skipped}, "
        f"total_keys={stats['total_keys']}, size={stats['total_size_mb']}MB, "
        f"elapsed={elapsed:.1f}s"
    )

    # Step 4: Notify Flask (optional, non-blocking)
    _notify_flask()


def _notify_flask() -> None:
    port = os.environ.get("PORT", "5000")
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/internal/cache-refreshed", timeout=2
        ):
            pass
    except Exception:
        pass   # Flask may not be running yet — that's fine


def main() -> None:
    parser = argparse.ArgumentParser(description="RouteCraft cache warmer")
    parser.add_argument("--once", action="store_true",
                        help="Run once immediately and exit (for testing)")
    parser.add_argument("--interval", type=int, default=30,
                        help="Run every N minutes (default: 30)")
    args = parser.parse_args()

    if args.once:
        log.info("Running cache warm once (--once mode)")
        warm_cache_job()
        return

    # Continuous mode — mirrors Airflow schedule
    try:
        import schedule
    except ImportError:
        log.error("'schedule' not installed. Run: pip install schedule")
        sys.exit(1)

    log.info(f"Cache warmer starting — will run every {args.interval} minutes")
    log.info("Press Ctrl+C to stop")

    # Run immediately on start, then on schedule
    warm_cache_job()
    schedule.every(args.interval).minutes.do(warm_cache_job)

    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    main()
