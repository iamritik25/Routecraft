"""
RouteCraft — Flask application (v2).

New in v2:
  - Structured JSON logging throughout
  - Pydantic v2 request validation on /v1/route
  - API versioning (/v1/*)
  - Rate limiting (flask-limiter)
  - Redis-backed graph cache (falls back to in-process dict)
  - Dynamic surge pricing (SurgePricingEngine)
  - A/B testing for LightGBM vs PyTorch MLP backends
  - Async route calculation: POST /v1/route/async → 202 + job_id
  - Job polling: GET /v1/jobs/<job_id>
  - ETA confidence intervals (P10/P50/P90) on every route
  - WebSocket live updates (flask-socketio)
  - /health and /metrics endpoints
"""

from __future__ import annotations

import os

# ---------------------------------------------------------------------------
# Load .env BEFORE anything else.
# Zero dependencies — pure stdlib. Works with or without python-dotenv.
# ---------------------------------------------------------------------------
def _load_dotenv(path: str = ".env") -> None:
    """Read key=value pairs from .env into os.environ (skips comments/blanks)."""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as _f:
        for _line in _f:
            _line = _line.strip()
            if not _line or _line.startswith("#") or "=" not in _line:
                continue
            _key, _, _val = _line.partition("=")
            _key = _key.strip()
            _val = _val.strip().strip('"').strip("'")
            if _key and _key not in os.environ:   # don't override real env vars
                os.environ[_key] = _val

_load_dotenv()

import json
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from flask import Flask, jsonify, render_template, request, redirect, Response
from urllib.parse import quote_plus

# Optional: pydantic for strict validation
try:
    from pydantic import ValidationError
    from schemas import RouteRequest as _RouteRequest
    _PYDANTIC_AVAILABLE = True
except ImportError:
    _PYDANTIC_AVAILABLE = False
    ValidationError = Exception  # fallback sentinel

from data_loader import DataLoader
from cost_engine import CostEngine
from distance_engine import DistanceEngine
from gtfs_engine import normalize_station_name
from graph_builder import MultiLayerGraphBuilder
from route_engine import RouteEngine, PathResult
from services.place_resolver import PlaceResolver, ResolvedInput
from services.geocoder import NominatimGeocoder
from surge_engine import SurgePricingEngine
from ab_testing import get_model_backend, get_backend_counts
from cache_backend import get_graph_cache
from job_store import get_job_store, Status
from schemas import RouteRequest
from logger import get_logger
import traffic_model as _traffic_model

# DiskCache — shared with Airflow cache warmer (pre-built graphs)
try:
    from disk_cache import DiskCache as _DiskCache
    _DISK_CACHE = _DiskCache(os.path.join(os.path.dirname(__file__), ".graph_cache"))
    log_tmp = get_logger(__name__)
except Exception:
    _DISK_CACHE = None

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Optional integrations (graceful if not installed)
# ---------------------------------------------------------------------------
try:
    from flask_limiter import Limiter  # type: ignore
    from flask_limiter.util import get_remote_address  # type: ignore
    _LIMITER_AVAILABLE = True
except Exception:
    _LIMITER_AVAILABLE = False

try:
    from flask_socketio import SocketIO, emit, join_room  # type: ignore
    _SOCKETIO_AVAILABLE = True
except Exception:
    _SOCKETIO_AVAILABLE = False

# ---------------------------------------------------------------------------
# Module-level metrics counters
# ---------------------------------------------------------------------------
_START_TIME = time.time()
_REQUEST_COUNT = 0
_TOTAL_RESPONSE_MS = 0.0
_TOTAL_EDGE_COUNT = 0
_ML_EDGE_COUNT = 0

_GRAPH_CACHE = get_graph_cache()
_JOB_STORE = get_job_store()
_SURGE_ENGINE = SurgePricingEngine()

socketio: Any = None  # set in create_app if available


def create_app() -> Flask:
    global socketio

    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "routecraft-dev-secret")

    # ── Rate limiting ──────────────────────────────────────────────────────
    if _LIMITER_AVAILABLE:
        limiter = Limiter(
            get_remote_address,
            app=app,
            default_limits=["200 per hour", "60 per minute"],
            storage_uri="memory://",
        )
    else:
        limiter = None

    # ── WebSocket ──────────────────────────────────────────────────────────
    if _SOCKETIO_AVAILABLE:
        socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

        @socketio.on("subscribe_route")
        def on_subscribe(data: dict) -> None:
            src = data.get("source", "")
            dst = data.get("destination", "")
            room = f"route:{src}:{dst}"
            join_room(room)
            log.info("Client subscribed to route room", extra={"room": room})

        @socketio.on("connect")
        def on_connect() -> None:
            log.info("WebSocket client connected")

    # ── Shared data (loaded once at startup) ──────────────────────────────
    data_loader = DataLoader(base_dir=".")
    geocoder = NominatimGeocoder()
    locations = data_loader.load_locations()
    alias_map = data_loader.load_aliases()

    name_to_coord: Dict[str, Tuple[float, float]] = {
        loc["name"]: (loc["lat"], loc["lon"]) for loc in locations
    }
    lower_name_lookup: Dict[str, str] = {
        loc["name"].lower(): loc["name"] for loc in locations
    }
    normalized_lookup: Dict[str, str] = {}
    for loc in locations:
        norm = normalize_station_name(loc["name"])
        normalized_lookup.setdefault(norm, loc["name"])

    log.info("RouteCraft startup", extra={"locations": len(locations), "aliases": len(alias_map)})

    def _bucket_hour(h: int) -> int:
        """Collapse 24 hours into 5 traffic-period buckets.

        This greatly increases graph-cache hit rate without losing meaningful
        traffic fidelity, because the ML model and heuristic rules only change
        behaviour at these boundaries:

          0-5   → 0  (night / off-peak)
          6-7   → 6  (early morning)
          8-11  → 8  (morning peak)
          12-15 → 12 (midday)
          16-22 → 17 (evening peak)
          23    → 23 (late night)
        """
        if h <= 5:  return 0
        if h <= 7:  return 6
        if h <= 11: return 8
        if h <= 15: return 12
        if h <= 22: return 17
        return 23

    # ── Helper: build or fetch graph (3-tier cache) ────────────────────────
    def _get_graph(hour: int, weather: str, backend: str) -> Tuple[Any, Any]:
        """
        3-tier cache lookup:
          Tier 1 — in-process dict  (microseconds, lost on restart)
          Tier 2 — Airflow DiskCache (milliseconds, survives restarts,
                                      pre-built every 30 min by DAG)
          Tier 3 — build from scratch (~25s cold, then promoted to T1+T2)
        """
        bucketed  = _bucket_hour(hour)
        cache_key = f"{bucketed}:{weather}:{backend}"

        # Tier 1: in-process cache (fastest)
        cached = _GRAPH_CACHE.get(cache_key)
        if cached is not None:
            return cached

        # Tier 2: Airflow pre-warmed DiskCache
        if _DISK_CACHE is not None:
            disk_hit = _DISK_CACHE.get(cache_key)
            if disk_hit is not None:
                log.info("DiskCache hit (Airflow pre-warmed)",
                         extra={"key": cache_key})
                _GRAPH_CACHE.set(cache_key, disk_hit)   # promote to T1
                return disk_hit

        # Tier 3: cold build
        log.info("Cold graph build", extra={"key": cache_key})
        os.environ["TRAFFIC_MODEL_TYPE"] = backend
        graph_builder = MultiLayerGraphBuilder(locations)
        graph         = graph_builder.build_graph(hour=bucketed, weather=weather)
        ml_snap       = _traffic_model.ml_summary()
        result        = (graph, ml_snap)

        _GRAPH_CACHE.set(cache_key, result)                     # promote to T1
        if _DISK_CACHE is not None:
            _DISK_CACHE.set(cache_key, result, ttl_seconds=3600)  # promote to T2

        log.info("Graph built and cached",
                 extra={"hour": bucketed, "weather": weather, "backend": backend})
        return result



    # ── Helper: serialise a PathResult to dict ─────────────────────────────
    def _serialize(result: Optional[PathResult], label: str) -> Dict[str, Any]:
        if result is None:
            return {
                "label": label, "path": [], "condensed_path": [],
                "modes": [], "edges": [], "total_cost": None, "total_time": None,
                "eta_p10": None, "eta_p50": None, "eta_p90": None, "eta_confidence": None,
            }

        def _condense(path):
            out, last = [], None
            for loc, _ in path:
                if loc != last:
                    out.append(loc)
                    last = loc
            return out

        def _summarize_edges(res: PathResult):
            if not res.path:
                return [], []
            summarized: List[Dict] = []
            display = [res.path[0][0]]
            for i, edge in enumerate(res.edges):
                fl, fm = res.path[i]
                tl, tm = res.path[i + 1]
                is_switch = fl == tl and fm != tm
                mode = edge.mode or tm
                if summarized and not is_switch:
                    prev = summarized[-1]
                    if prev.get("mode") == mode and not prev.get("is_switch"):
                        prev["to"] = f"{tl} ({tm})"
                        prev["time_min"] = round(float(prev["time_min"]) + edge.time_min, 1)
                        prev["cost"] = round(float(prev["cost"]) + edge.cost, 1)
                        prev["to_loc"] = tl
                        prev["description"] = f"{mode} from {prev['from_loc']} to {tl}"
                        continue
                summarized.append({
                    "from": f"{fl} ({fm})", "to": f"{tl} ({tm})",
                    "from_loc": fl, "to_loc": tl, "mode": mode,
                    "is_switch": is_switch, "description": edge.description,
                    "time_min": round(edge.time_min, 1), "cost": round(edge.cost, 1),
                })
                if display[-1] != tl:
                    display.append(tl)

            display = [res.path[0][0]]
            for item in summarized:
                tl = item.get("to_loc") or ""
                if tl and display[-1] != tl:
                    display.append(tl)
            for item in summarized:
                for k in ("from_loc", "to_loc", "mode", "is_switch"):
                    item.pop(k, None)
            return summarized, display

        edges, condensed = _summarize_edges(result)
        return {
            "label": label,
            "path": [f"{l} ({m})" for l, m in result.path],
            "condensed_path": condensed or _condense(result.path),
            "modes": [s[1] for s in result.path],
            "edges": edges,
            "total_cost": round(result.total_cost, 1),
            "total_time": round(result.total_time, 1),
            "eta_p10": result.eta_p10,
            "eta_p50": result.eta_p50,
            "eta_p90": result.eta_p90,
            "eta_confidence": result.eta_confidence,
        }

    # ── Core routing logic (shared by sync + async endpoints) ───────────────
    def _compute_routes(payload: dict) -> Tuple[dict, int]:
        global _REQUEST_COUNT, _TOTAL_RESPONSE_MS, _TOTAL_EDGE_COUNT, _ML_EDGE_COUNT
        t0 = time.time()
        _traffic_model.reset_ml_state()

        if _PYDANTIC_AVAILABLE:
            try:
                req = _RouteRequest(**payload)
                raw_source = req.source
                raw_destination = req.destination
                preference = req.preference
                hour = req.hour
                weather = req.weather
            except Exception as exc:
                return {"error": "Invalid request", "details": str(exc)}, 400
        else:
            # Fallback validation without pydantic
            raw_source = str(payload.get("source") or "").strip()
            raw_destination = str(payload.get("destination") or "").strip()
            preference = str(payload.get("preference", "balanced")).lower().strip()
            weather = str(payload.get("weather", "Clear")).strip()
            try:
                hour = max(0, min(23, int(payload.get("hour", 9))))
            except (TypeError, ValueError):
                hour = 9
            if not raw_source or not raw_destination:
                return {"error": "source and destination are required"}, 400
            if preference not in ("cheapest", "fastest", "balanced"):
                preference = "balanced"


        # Session-based A/B backend selection
        session_id = payload.get("session_id")
        backend = get_model_backend(session_id)

        resolver = PlaceResolver(locations=locations, alias_map=alias_map, base_dir=".")
        resolved_source = resolver.resolve(raw_source)
        resolved_destination = resolver.resolve(raw_destination)

        if resolved_source is None:
            coords = geocoder.geocode(raw_source)
            if coords:
                resolved_source = ResolvedInput(
                    kind="place", name=raw_source,
                    lat=coords[0], lon=coords[1], place_type="geocoded",
                )
        if resolved_destination is None:
            coords = geocoder.geocode(raw_destination)
            if coords:
                resolved_destination = ResolvedInput(
                    kind="place", name=raw_destination,
                    lat=coords[0], lon=coords[1], place_type="geocoded",
                )

        if resolved_source is None or resolved_destination is None:
            return {"error": "Unknown source or destination"}, 400

        def get_coord(r: ResolvedInput):
            if r.kind == "transport":
                return name_to_coord.get(r.name)
            if r.lat is not None and r.lon is not None:
                return float(r.lat), float(r.lon)
            return None

        src_coord = get_coord(resolved_source)
        dst_coord = get_coord(resolved_destination)
        if not src_coord or not dst_coord:
            return {"error": "Missing coordinates"}, 400

        source = resolved_source.name
        destination = resolved_destination.name
        dist_km = DistanceEngine().haversine(src_coord, dst_coord)

        # Surge pricing
        surge_mult = _SURGE_ENGINE.get_surge(hour, weather, area=source)
        surge_label = _SURGE_ENGINE.get_surge_label(surge_mult)
        surge_info = {"multiplier": surge_mult, "label": surge_label}

        if resolved_source.kind == "transport" and resolved_destination.kind == "transport":
            graph, ml_snap = _get_graph(hour, weather, backend)
            engine = RouteEngine(graph)
            routes = engine.compute_pareto_routes(source, destination)

            preferred_key = {"cheapest": "cheapest", "fastest": "fastest", "balanced": "balanced"}.get(preference, "balanced")

            # Track metrics
            ml_sum = _traffic_model.ml_summary()
            _TOTAL_EDGE_COUNT += ml_sum.get("hits", 0) + ml_sum.get("heuristic_hits", 0)
            _ML_EDGE_COUNT += ml_sum.get("hits", 0)

            response = {
                "cheapest": _serialize(routes["cheapest"], "Cheapest Route"),
                "fastest": _serialize(routes["fastest"], "Fastest Route"),
                "balanced": _serialize(routes["balanced"], "Balanced Route"),
                "cab_only": _serialize(routes["cab_only"], "Cab Only"),
                "metro_only": _serialize(routes["metro_only"], "Metro Only"),
                "metro_plus_cab": _serialize(routes["metro_plus_cab"], "Metro + Cab"),
                "bus_only": _serialize(routes["bus_only"], "BMTC Bus Only"),
                "preferred": preferred_key,
                "ml": ml_snap,
                "surge": surge_info,
                "ab_backend": backend,
            }
        else:
            # Simplified routing for place-based inputs
            ce = CostEngine()
            SPEEDS = {"walk": 5.0, "auto": 22.0, "cab": 35.0}

            def mins(d, spd): return (d / max(spd, 0.001)) * 60.0

            cab_t = mins(dist_km, SPEEDS["cab"])
            cab_c = ce.cost("cab", dist_km) * surge_mult
            fastest = {
                "label": "Fastest Route", "path": [source, destination],
                "condensed_path": [source, destination], "modes": ["cab"],
                "edges": [{"from": source, "to": destination, "description": f"cab from {source} to {destination}",
                           "time_min": round(cab_t, 1), "cost": round(cab_c, 1)}],
                "total_cost": round(cab_c, 1), "total_time": round(cab_t, 1),
                "eta_p10": round(cab_t * 0.85, 1), "eta_p50": round(cab_t, 1),
                "eta_p90": round(cab_t * 1.25, 1), "eta_confidence": "medium",
            }
            if dist_km <= 0.4:
                cheap_t = mins(dist_km, SPEEDS["walk"]); cheap_c = 0.0; cheap_mode = "walk"
            else:
                cheap_t = mins(dist_km, SPEEDS["auto"]); cheap_c = ce.cost("auto", dist_km); cheap_mode = "auto"
            cheapest = {
                "label": "Cheapest Route", "path": [source, destination],
                "condensed_path": [source, destination], "modes": [cheap_mode],
                "edges": [{"from": source, "to": destination, "description": f"{cheap_mode} from {source} to {destination}",
                           "time_min": round(cheap_t, 1), "cost": round(cheap_c, 1)}],
                "total_cost": round(cheap_c, 1), "total_time": round(cheap_t, 1),
                "eta_p10": round(cheap_t * 0.85, 1), "eta_p50": round(cheap_t, 1),
                "eta_p90": round(cheap_t * 1.30, 1), "eta_confidence": "low",
            }
            empty = lambda lbl: {"label": lbl, "path": [], "condensed_path": [], "modes": [],
                                  "edges": [], "total_cost": None, "total_time": None,
                                  "eta_p10": None, "eta_p50": None, "eta_p90": None, "eta_confidence": None}
            response = {
                "cheapest": cheapest, "fastest": fastest, "balanced": fastest,
                "cab_only": fastest, "metro_only": empty("Metro Only"),
                "metro_plus_cab": fastest, "bus_only": empty("BMTC Bus Only"),
                "preferred": preference, "ml": _traffic_model.ml_summary(),
                "surge": surge_info, "ab_backend": backend,
            }

        elapsed_ms = (time.time() - t0) * 1000
        _REQUEST_COUNT += 1
        _TOTAL_RESPONSE_MS += elapsed_ms
        log.info("Route computed", extra={"source": source, "destination": destination,
                                          "backend": backend, "elapsed_ms": round(elapsed_ms, 1)})
        return response, 200

    # ══════════════════════════════════════════════════════════════════════
    # Routes
    # ══════════════════════════════════════════════════════════════════════

    @app.route("/")
    def index() -> Any:
        location_names = [loc["name"] for loc in locations]
        location_coords = {loc["name"]: [loc["lat"], loc["lon"]] for loc in locations}
        return render_template(
            "index.html",
            locations=location_names,
            location_coords_json=json.dumps(location_coords),
        )

    # ── v1 versioned route endpoint ────────────────────────────────────────
    @app.route("/v1/route", methods=["POST"])
    def v1_route() -> Any:
        payload = request.get_json(force=True) or {}
        result, status = _compute_routes(payload)
        return jsonify(result), status

    # ── Legacy endpoint (backward compat) ─────────────────────────────────
    @app.route("/api/route", methods=["POST"])
    def api_route() -> Any:
        payload = request.get_json(force=True) or {}
        result, status = _compute_routes(payload)
        return jsonify(result), status

    # ── Async route: POST returns 202 + job_id immediately ─────────────────
    @app.route("/v1/route/async", methods=["POST"])
    def v1_route_async() -> Any:
        payload = request.get_json(force=True) or {}
        job_id = _JOB_STORE.create()

        def _worker():
            _JOB_STORE.set_processing(job_id)
            try:
                result, _ = _compute_routes(payload)
                _JOB_STORE.set_done(job_id, result)
                # Push result via WebSocket if available
                if _SOCKETIO_AVAILABLE and socketio:
                    src = payload.get("source", "")
                    dst = payload.get("destination", "")
                    socketio.emit("route_update", {"job_id": job_id, "result": result},
                                  room=f"route:{src}:{dst}")
            except Exception as exc:
                _JOB_STORE.set_failed(job_id, str(exc))
                log.error("Async route job failed", extra={"job_id": job_id, "error": str(exc)})

        threading.Thread(target=_worker, daemon=True).start()
        return jsonify({
            "job_id": job_id,
            "status": "pending",
            "poll_url": f"/v1/jobs/{job_id}",
            "message": "Route calculation started. Poll poll_url for result.",
        }), 202

    # ── Job status polling ─────────────────────────────────────────────────
    @app.route("/v1/jobs/<job_id>", methods=["GET"])
    def v1_job_status(job_id: str) -> Any:
        job = _JOB_STORE.get(job_id)
        if job is None:
            return jsonify({"error": "Job not found"}), 404
        return jsonify({
            "job_id": job.job_id,
            "status": job.status.value,
            "result": job.result,
            "error":  job.error,
        })

    # ── Internal: Airflow cache-refresh notification ───────────────────────
    @app.route("/internal/cache-refreshed", methods=["GET", "POST"])
    def internal_cache_refreshed() -> Any:
        """
        Called by the Airflow cache_warmer_dag after each warm run.
        Evicts stale in-process (T1) entries so the next request
        pulls the fresher version from DiskCache (T2).
        Only accessible from localhost for security.
        """
        if request.remote_addr not in ("127.0.0.1", "::1"):
            return jsonify({"error": "forbidden"}), 403

        evicted = 0
        if _DISK_CACHE is not None:
            # Find all keys present in DiskCache and clear them from T1
            for key in _DISK_CACHE.keys():
                if _GRAPH_CACHE.get(key) is not None:
                    # Force next request to re-read from DiskCache
                    try:
                        _GRAPH_CACHE._store.pop(key, None)  # type: ignore[attr-defined]
                        evicted += 1
                    except Exception:
                        pass
            stats = _DISK_CACHE.stats()
        else:
            stats = {}

        log.info("Airflow cache refresh received",
                 extra={"evicted_t1_keys": evicted, "disk_stats": stats})
        return jsonify({
            "status":      "refreshed",
            "evicted_t1":  evicted,
            "disk_cache":  stats,
        })


    # ── Health check ───────────────────────────────────────────────────────
    @app.route("/health")
    def health() -> Any:
        try:
            from services.traffic_ml import get_predictor
            ml_status = "loaded" if get_predictor().available else "fallback"
        except Exception:
            ml_status = "unavailable"
        return jsonify({
            "status": "healthy",
            "ml_model": ml_status,
            "graph_cache_size": _GRAPH_CACHE.size,
            "cache_backend": _GRAPH_CACHE.backend_name,
            "uptime_seconds": round(time.time() - _START_TIME, 1),
        })

    # ── Metrics ───────────────────────────────────────────────────────────
    @app.route("/metrics")
    def metrics() -> Any:
        return jsonify({
            "total_requests": _REQUEST_COUNT,
            "cache_hits": _GRAPH_CACHE.hit_count,
            "cache_misses": _GRAPH_CACHE.miss_count,
            "avg_response_ms": round(_TOTAL_RESPONSE_MS / max(_REQUEST_COUNT, 1), 1),
            "ml_hit_rate": round(_ML_EDGE_COUNT / max(_TOTAL_EDGE_COUNT, 1), 3),
            "ab_backend_counts": get_backend_counts(),
            "uptime_seconds": round(time.time() - _START_TIME, 1),
        })

    # ── Booking deep-links ─────────────────────────────────────────────────
    @app.route("/book/uber")
    def book_uber() -> Any:
        src, dst = _resolve_booking_params()
        if not src or not dst:
            return "Invalid source or destination", 400
        lat1, lon1 = name_to_coord[src]
        lat2, lon2 = name_to_coord[dst]
        url = (
            "https://m.uber.com/ul/?action=setPickup"
            f"&pickup[latitude]={lat1}&pickup[longitude]={lon1}"
            f"&dropoff[latitude]={lat2}&dropoff[longitude]={lon2}"
            f"&pickup[formatted_address]={quote_plus(src)}"
            f"&dropoff[formatted_address]={quote_plus(dst)}"
        )
        return redirect(url)

    @app.route("/book/metro")
    @app.route("/book/bmtc")
    def book_transit() -> Any:
        src, dst = _resolve_booking_params()
        if not src or not dst:
            return "Invalid source or destination", 400
        lat1, lon1 = name_to_coord[src]
        lat2, lon2 = name_to_coord[dst]
        url = (
            "https://www.google.com/maps/dir/?api=1"
            f"&origin={quote_plus(f'{lat1},{lon1}')}"
            f"&destination={quote_plus(f'{lat2},{lon2}')}"
            "&travelmode=transit"
        )
        return redirect(url)

    def _resolve_booking_params() -> Tuple[Optional[str], Optional[str]]:
        raw_src = (request.args.get("source") or "").strip().lower()
        raw_dst = (request.args.get("destination") or "").strip().lower()
        src = lower_name_lookup.get(raw_src)
        dst = lower_name_lookup.get(raw_dst)
        if not src or not dst or src not in name_to_coord or dst not in name_to_coord:
            return None, None
        return src, dst

    # ── Background pre-warm ────────────────────────────────────────────────
    def _prewarm() -> None:
        """Build the two most-requested graph variants at startup so the first
        real user request is always a cache hit, not a 25-second cold build."""
        try:
            ab_backend = os.environ.get("TRAFFIC_MODEL_TYPE", "lightgbm")
            for _h, _w in [(8, "Clear"), (17, "Clear")]:
                _get_graph(_h, _w, ab_backend)
                log.info("Pre-warm complete", extra={"hour": _h, "weather": _w})
        except Exception as exc:
            log.warning("Pre-warm failed", extra={"error": str(exc)})

    _prewarm_thread = threading.Thread(target=_prewarm, daemon=True, name="prewarm")
    _prewarm_thread.start()
    log.info("Background pre-warm started — first request will be fast once ready")

    return app


if __name__ == "__main__":
    application = create_app()
    if _SOCKETIO_AVAILABLE and socketio:
        socketio.run(application, debug=True, use_reloader=False, port=5000)
    else:
        application.run(debug=True, use_reloader=False, port=5000)
