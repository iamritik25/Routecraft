import re
import time as _time
from dataclasses import dataclass
from typing import Dict, List, Tuple, Set, Optional

from distance_engine import DistanceEngine
from cost_engine import CostEngine
from time_engine import SegmentTimeBreakdown, calculate_segment_time, calculate_segment_cost
from gtfs_engine import normalize_station_name
from data_loader import DataLoader
from config import (
    MAX_WALK_KM,
    MAX_AUTO_CONNECTOR_KM,
    MODE_SWITCH_COST,
    MODE_SWITCH_TIME_MIN,
    AIRPORT_NODE_NAMES,
    AIRPORT_RESTRICTED_FINAL_MODES,
)
from services.metro_graph_builder import integrate_metro_layer


TRANSPORT_SPEED_KMPH = {
    "walk": 5.0,
    "auto": 25.0,
    "cab": 35.0,
    "metro": 45.0,
    "bus": 18.0,
}

BMTC_GTFS_FOLDER = "data/bmtc_gtfs"
BMTC_STOP_MATCH_RADIUS_KM = 1.5
BMTC_ROUTE_ENDPOINT_MATCH_RADIUS_KM = 3.0

# ---------------------------------------------------------------------------
# Module-level GTFS cache — raw CSV/TXT files are read ONCE per process.
# Subsequent build_graph() calls reuse the already-parsed data.
# ---------------------------------------------------------------------------
_GTFS_CACHE: Dict[str, dict] = {}          # keyed by folder path
_PROXIMITY_CACHE: Dict[str, dict] = {}     # keyed by (folder_path, loc_hash)


def _load_gtfs_cached(base_dir: str, folder: str) -> dict:
    """Return parsed GTFS feed, reading from disk only on the first call."""
    key = f"{base_dir}::{folder}"
    if key not in _GTFS_CACHE:
        dl = DataLoader(base_dir=base_dir)
        _GTFS_CACHE[key] = dl.load_gtfs_data(folder)
    return _GTFS_CACHE[key]



def _parse_hhmmss(t: str) -> Optional[int]:
    if not t:
        return None
    parts = t.split(":")
    if len(parts) != 3:
        return None
    try:
        h = int(parts[0])
        m = int(parts[1])
        s = int(parts[2])
    except ValueError:
        return None
    return h * 60 + m + s // 60


@dataclass
class Edge:
    target: Tuple[str, str]  # (location, mode)
    time_min: float
    cost: float
    description: str
    # Extended breakdown fields (used in the API response)
    distance_km: float = 0.0
    base_time_min: float = 0.0
    traffic_multiplier: float = 1.0
    weather_multiplier: float = 1.0
    fixed_delay_min: float = 0.0
    final_time_min: float = 0.0
    mode: str = ""
    route_source: str = "synthetic"  # or "gtfs"
    route_id: str | None = None


class MultiLayerGraphBuilder:
    """
    Builds a multi-layer transport graph for Bangalore.

    Nodes are of the form (location_name, mode).
    Edges exist between locations for the same mode, and between modes for the same location.
    """

    def __init__(self, locations: List[Dict[str, float]], base_dir: str = ".") -> None:
        self.locations = locations
        self.base_dir = base_dir
        self.distance_engine = DistanceEngine()
        self.cost_engine = CostEngine()
        self.data_loader = DataLoader(base_dir=self.base_dir)

        # Metro layer is dataset-driven (OpenCity KML/CSV) and integrated at build time.

    def build_graph(
        self,
        hour: int,
        weather: str,
    ) -> Dict[Tuple[str, str], List[Edge]]:
        """
        Build adjacency list representation of the multi-layer graph.
        GTFS data and proximity mapping are cached at module level so
        repeated calls for different (hour, weather) pairs are fast.
        """
        coord_map: Dict[str, Tuple[float, float]] = {
            loc["name"]: (loc["lat"], loc["lon"]) for loc in self.locations
        }
        norm_to_loc: Dict[str, str] = {
            normalize_station_name(name): name for name in coord_map.keys()
        }

        # ── GTFS data: read from disk once, then served from module cache ──
        bmtc_feed     = _load_gtfs_cached(self.base_dir, BMTC_GTFS_FOLDER)
        bmtc_stops     = bmtc_feed.get("stops", [])
        bmtc_routes    = bmtc_feed.get("routes", [])
        bmtc_trips     = bmtc_feed.get("trips", [])
        bmtc_stop_times = bmtc_feed.get("stop_times", [])
        if not bmtc_stops or not bmtc_routes or not bmtc_trips or not bmtc_stop_times:
            print("[BMTC GTFS] Missing one or more GTFS files in data/bmtc_gtfs; bus graph may be empty.")
        else:
            print(
                f"[BMTC GTFS] Loaded stops={len(bmtc_stops)}, routes={len(bmtc_routes)}, "
                f"trips={len(bmtc_trips)}, stop_times={len(bmtc_stop_times)}."
            )

        # ── Proximity mapping: 4433 stops × 69 locations = 305k haversines.
        #    Cache the result keyed by location set hash so it is computed
        #    only once per unique location list (across all hour/weather combos).
        _prox_key = f"{self.base_dir}::prox::{hash(tuple(sorted(coord_map.keys())))}"
        _t0 = _time.perf_counter()
        if _prox_key in _PROXIMITY_CACHE:
            _cached_prox = _PROXIMITY_CACHE[_prox_key]
            bmtc_stop_id_to_loc_name: Dict[str, str] = _cached_prox["stop_id_to_loc"]
            bmtc_bus_stops: Set[str]                 = _cached_prox["bus_stops"]
            mapped_stop_name_pairs: List[Tuple[str, str]] = _cached_prox["name_pairs"]
            print(f"[BMTC GTFS] Proximity mapping: loaded from cache ({len(bmtc_stop_id_to_loc_name)} stops).")
        else:
            bmtc_stop_id_to_loc_name = {}
            bmtc_bus_stops = set()
            mapped_stop_name_pairs = []
            skipped_unmapped_bmtc_stops = 0
            mapped_by_name = 0
            mapped_by_proximity = 0
            location_names = list(coord_map.keys())
            for row in bmtc_stops:
                stop_id = str(row.get("stop_id", "")).strip()
                name = str(row.get("stop_name", "")).strip()
                lat = row.get("stop_lat")
                lon = row.get("stop_lon")
                if not stop_id or not name or lat in (None, "") or lon in (None, ""):
                    continue
                try:
                    lat_f = float(lat)
                    lon_f = float(lon)
                except ValueError:
                    continue

                key = normalize_station_name(name)
                if key in norm_to_loc:
                    loc_name = norm_to_loc[key]
                    mapped_by_name += 1
                else:
                    best_name: Optional[str] = None
                    best_dist_km = float("inf")
                    for loc_name_candidate in location_names:
                        d = self.distance_engine.haversine(
                            (lat_f, lon_f),
                            coord_map[loc_name_candidate],
                        )
                        if d < best_dist_km:
                            best_dist_km = d
                            best_name = loc_name_candidate
                    if best_name is None or best_dist_km > BMTC_STOP_MATCH_RADIUS_KM:
                        skipped_unmapped_bmtc_stops += 1
                        continue
                    loc_name = best_name
                    mapped_by_proximity += 1

                bmtc_stop_id_to_loc_name[stop_id] = loc_name
                bmtc_bus_stops.add(loc_name)
                mapped_stop_name_pairs.append((key, loc_name))

            _elapsed_prox = _time.perf_counter() - _t0
            print(
                f"[BMTC GTFS] Mapped stops to project locations: {len(bmtc_stop_id_to_loc_name)} "
                f"(by_name={mapped_by_name}, by_proximity={mapped_by_proximity}, "
                f"skipped unmatched: {skipped_unmapped_bmtc_stops}) in {_elapsed_prox*1000:.0f}ms"
            )
            _PROXIMITY_CACHE[_prox_key] = {
                "stop_id_to_loc": bmtc_stop_id_to_loc_name,
                "bus_stops": bmtc_bus_stops,
                "name_pairs": mapped_stop_name_pairs,
            }


        metro_stations: Set[str] = set()
        major_bus_hubs: Set[str] = {
            loc["name"] for loc in self.locations if bool(loc.get("is_bus_hub", False))
        }
        bus_hubs: Set[str] = set(major_bus_hubs)
        bus_hubs.update(bmtc_bus_stops)

        modes = ["walk", "auto", "cab", "bus", "metro"]
        graph: Dict[Tuple[str, str], List[Edge]] = {}

        # Initialize nodes
        for name in coord_map:
            for mode in modes:
                graph[(name, mode)] = []

        # Connect all locations pairwise for each mode
        names = list(coord_map.keys())
        n = len(names)
        for i in range(n):
            for j in range(i + 1, n):
                src_name = names[i]
                dst_name = names[j]
                dist_km = self.distance_engine.haversine(coord_map[src_name], coord_map[dst_name])

                for mode in modes:
                    mode_l = mode
                    # Walking: enforce realism – no segment longer than MAX_WALK_KM.
                    if mode_l == "walk" and dist_km > MAX_WALK_KM:
                        continue
                    # Metro edges now come from GTFS, skip synthetic metro connections.
                    if mode_l == "metro":
                        continue
                    # BMTC bus edges are added separately from route data below (including airport routes).
                    if mode_l == "bus":
                        continue

                    # Airport access constraint:
                    # block direct auto edges to/from the airport terminal node.
                    if mode_l == "auto" and (
                        src_name in AIRPORT_NODE_NAMES or dst_name in AIRPORT_NODE_NAMES
                    ):
                        continue
                    # First/last-mile alignment: prioritise realistic connectors.
                    # We still allow auto/cab as city-wide modes but keep walking constrained.
                    breakdown: SegmentTimeBreakdown = calculate_segment_time(
                        distance_km=dist_km,
                        mode=mode_l,
                        hour=hour,
                        weather=weather,
                        source=src_name,
                        destination=dst_name,
                    )
                    cost = calculate_segment_cost(
                        distance_km=dist_km,
                        mode=mode_l,
                        traffic_mult=breakdown.traffic_multiplier,
                        weather_mult=breakdown.weather_multiplier,
                    )

                    # Undirected edges (both directions)
                    edge_desc = f"{mode_l} from {src_name} to {dst_name}"
                    graph[(src_name, mode)].append(
                        Edge(
                            target=(dst_name, mode_l),
                            time_min=breakdown.final_time_min,
                            cost=cost,
                            description=edge_desc,
                            distance_km=breakdown.distance_km,
                            base_time_min=breakdown.base_time_min,
                            traffic_multiplier=breakdown.traffic_multiplier,
                            weather_multiplier=breakdown.weather_multiplier,
                            fixed_delay_min=breakdown.fixed_delay_min,
                            final_time_min=breakdown.final_time_min,
                            mode=mode_l,
                        )
                    )
                    edge_desc_back = f"{mode_l} from {dst_name} to {src_name}"
                    graph[(dst_name, mode)].append(
                        Edge(
                            target=(src_name, mode_l),
                            time_min=breakdown.final_time_min,
                            cost=cost,
                            description=edge_desc_back,
                            distance_km=breakdown.distance_km,
                            base_time_min=breakdown.base_time_min,
                            traffic_multiplier=breakdown.traffic_multiplier,
                            weather_multiplier=breakdown.weather_multiplier,
                            fixed_delay_min=breakdown.fixed_delay_min,
                            final_time_min=breakdown.final_time_min,
                            mode=mode_l,
                        )
                    )

        # Curated landmark connectors: allow multiple explicit first-mile / last-mile options.
        landmark_connectors = self.data_loader.load_landmark_connectors()
        if landmark_connectors:
            print(f"[DATA] Loaded {len(landmark_connectors)} landmark connectors.")
        for conn in landmark_connectors:
            src = conn.get("source")
            dst = conn.get("target")
            mode_l = str(conn.get("mode", "")).lower() or "auto"
            if not src or not dst or src not in coord_map or dst not in coord_map:
                continue
            dist_km = float(conn.get("distance_km", self.distance_engine.haversine(coord_map[src], coord_map[dst])))
            # Enforce walking cap even for curated data.
            if mode_l == "walk" and dist_km > MAX_WALK_KM:
                continue
            breakdown = calculate_segment_time(
                distance_km=dist_km,
                mode=mode_l,
                hour=hour,
                weather=weather,
                source=src,
                destination=dst,
            )
            cost = calculate_segment_cost(
                distance_km=dist_km,
                mode=mode_l,
                traffic_mult=breakdown.traffic_multiplier,
                weather_mult=breakdown.weather_multiplier,
            )
            route_source = str(conn.get("route_source", "landmark_connector"))
            desc = f"{mode_l} connector from {src} to {dst}"
            graph[(src, mode_l)].append(
                Edge(
                    target=(dst, mode_l),
                    time_min=breakdown.final_time_min,
                    cost=cost,
                    description=desc,
                    distance_km=breakdown.distance_km,
                    base_time_min=breakdown.base_time_min,
                    traffic_multiplier=breakdown.traffic_multiplier,
                    weather_multiplier=breakdown.weather_multiplier,
                    fixed_delay_min=breakdown.fixed_delay_min,
                    final_time_min=breakdown.final_time_min,
                    mode=mode_l,
                    route_source=route_source,
                )
            )

        # Integrate dataset-driven metro layer (OpenCity KML/CSV).
        coord_map, _added_stations, _added_edges, metro_station_names = integrate_metro_layer(
            coord_map=coord_map,
            graph=graph,
            hour=hour,
            weather=weather,
            metro_dir="data/metro",
        )
        metro_stations = set(metro_station_names)

        # Add BMTC bus edges from GTFS stop_times (directed, scheduled-time weights).
        route_type_by_id: Dict[str, str] = {}
        for r in bmtc_routes:
            route_id = str(r.get("route_id", "")).strip()
            if route_id:
                route_type_by_id[route_id] = str(r.get("route_type", "")).strip()

        # Prefer GTFS bus route_type=3; if unavailable, keep all routes.
        bus_route_ids = {rid for rid, rtype in route_type_by_id.items() if rtype == "3"}
        if not bus_route_ids:
            bus_route_ids = set(route_type_by_id.keys())

        bus_trip_to_route: Dict[str, str] = {}
        for tr in bmtc_trips:
            trip_id = str(tr.get("trip_id", "")).strip()
            route_id = str(tr.get("route_id", "")).strip()
            if not trip_id or not route_id:
                continue
            if bus_route_ids and route_id not in bus_route_ids:
                continue
            bus_trip_to_route[trip_id] = route_id

        times_by_trip: Dict[str, List[Dict[str, str]]] = {}
        for row in bmtc_stop_times:
            trip_id = str(row.get("trip_id", "")).strip()
            if trip_id not in bus_trip_to_route:
                continue
            times_by_trip.setdefault(trip_id, []).append(row)

        edge_best: Dict[Tuple[str, str], Tuple[float, float, str]] = {}
        for trip_id, rows in times_by_trip.items():
            route_id = bus_trip_to_route[trip_id]
            try:
                ordered = sorted(rows, key=lambda r: int(r.get("stop_sequence", "0")))
            except ValueError:
                ordered = rows

            for i in range(len(ordered) - 1):
                a = ordered[i]
                b = ordered[i + 1]
                stop_a = str(a.get("stop_id", "")).strip()
                stop_b = str(b.get("stop_id", "")).strip()
                if stop_a not in bmtc_stop_id_to_loc_name or stop_b not in bmtc_stop_id_to_loc_name:
                    continue

                src_name = bmtc_stop_id_to_loc_name[stop_a]
                dst_name = bmtc_stop_id_to_loc_name[stop_b]
                if src_name not in coord_map or dst_name not in coord_map:
                    continue

                t_dep = _parse_hhmmss(a.get("departure_time", "") or a.get("arrival_time", ""))
                t_arr = _parse_hhmmss(b.get("arrival_time", "") or b.get("departure_time", ""))
                if t_dep is None or t_arr is None or t_arr <= t_dep:
                    continue

                scheduled_time_min = float(t_arr - t_dep)
                distance_km = self.distance_engine.haversine(coord_map[src_name], coord_map[dst_name])
                key = (src_name, dst_name)
                prev = edge_best.get(key)
                if prev is None or scheduled_time_min < prev[1]:
                    edge_best[key] = (distance_km, scheduled_time_min, route_id)

        # Fallback builder: if stop_times is non-sequential (e.g., only one stop per
        # trip), derive coarse bus links from route endpoints in routes.txt.
        if not edge_best and bmtc_routes:
            print("[BMTC GTFS] stop_times has no usable consecutive pairs. Falling back to route endpoint links.")

            stop_words = {
                "bus", "station", "stand", "ttmc", "mall", "cross", "circle",
                "layout", "town", "road", "gate", "complex",
            }

            def _token_set(s: str) -> Set[str]:
                return {t for t in normalize_station_name(s).split(" ") if t and t not in stop_words}

            def resolve_route_endpoint(raw_name: str) -> Optional[str]:
                name = (raw_name or "").strip()
                if not name:
                    return None
                candidates = [p.strip() for p in re.split(r"[/,(]", name) if p.strip()]
                if not candidates:
                    candidates = [name]

                best_loc: Optional[str] = None
                best_score = 0
                for cand in candidates:
                    key = normalize_station_name(cand)
                    if key in norm_to_loc:
                        return norm_to_loc[key]

                    # Match against mapped GTFS stop names:
                    # - direct containment either way
                    # - token overlap scoring
                    tokens = _token_set(key)
                    for stop_key, mapped_loc in mapped_stop_name_pairs:
                        if key in stop_key or stop_key in key:
                            return mapped_loc
                        stop_tokens = _token_set(stop_key)
                        score = len(tokens.intersection(stop_tokens))
                        if score > best_score:
                            best_score = score
                            best_loc = mapped_loc
                # Require stronger match quality for fallback.
                if best_loc is not None and best_score >= 2:
                    return best_loc
                return None

            fallback_added = 0
            for r in bmtc_routes:
                route_id = str(r.get("route_id", "")).strip()
                long_name = str(r.get("route_long_name", "")).strip() or str(r.get("route_desc", "")).strip()
                if not route_id or not long_name:
                    continue

                parts = [p.strip() for p in re.split(r"\s*[-–]\s*", long_name) if p.strip()]
                if len(parts) < 2:
                    continue
                src_res = resolve_route_endpoint(parts[0])
                dst_res = resolve_route_endpoint(parts[-1])
                if not src_res or not dst_res or src_res == dst_res:
                    continue
                if src_res not in coord_map or dst_res not in coord_map:
                    continue
                if route_id.upper().startswith("KIAS"):
                    # Keep airport fallback routes anchored to major bus hubs only.
                    if src_res not in major_bus_hubs:
                        continue

                dist_km = self.distance_engine.haversine(coord_map[src_res], coord_map[dst_res])
                if dist_km <= 0.1 or dist_km > 70.0:
                    continue
                est_time_min = (dist_km / 18.0) * 60.0
                # Prefer realistic airport boarding points (major hubs) in fallback
                # so routes don't detour through arbitrary commercial endpoints.
                if route_id.upper().startswith("KIAS") and src_res not in bus_hubs:
                    est_time_min += 20.0
                k1 = (src_res, dst_res)
                k2 = (dst_res, src_res)
                if k1 not in edge_best:
                    edge_best[k1] = (dist_km, est_time_min, route_id)
                    fallback_added += 1
                if k2 not in edge_best:
                    edge_best[k2] = (dist_km, est_time_min, route_id)
                    fallback_added += 1
            print(f"[BMTC GTFS] Fallback endpoint edges added: {fallback_added}")

        for (src_name, dst_name), (distance_km, scheduled_time_min, route_id) in edge_best.items():
            cost = calculate_segment_cost(
                distance_km=distance_km,
                mode="bus",
                traffic_mult=1.0,
                weather_mult=1.0,
            )
            desc = f"bus (BMTC GTFS route {route_id or '?'}) from {src_name} to {dst_name}"
            graph[(src_name, "bus")].append(
                Edge(
                    target=(dst_name, "bus"),
                    time_min=scheduled_time_min,
                    cost=cost,
                    description=desc,
                    distance_km=distance_km,
                    base_time_min=scheduled_time_min,
                    traffic_multiplier=1.0,
                    weather_multiplier=1.0,
                    fixed_delay_min=0.0,
                    final_time_min=scheduled_time_min,
                    mode="bus",
                    route_source="gtfs",
                    route_id=route_id,
                )
            )
        print(f"[BMTC GTFS] Integrated directed bus edges: {len(edge_best)}")

        # Transfer edges: connect metro stations to nearby bus hubs via walking.
        # This enables bus ↔ metro multimodal routing.
        if metro_stations:
            from distance_engine import DistanceEngine  # local import to avoid cycles

            de = DistanceEngine()
            transfer_count = 0
            for ms in metro_stations:
                if ms not in coord_map:
                    continue
                ms_coord = coord_map[ms]
                for bh in bus_hubs:
                    if bh not in coord_map:
                        continue
                    d_km = de.haversine(ms_coord, coord_map[bh])
                    if d_km > 0.5:
                        continue
                    time_min = (d_km / 5.0) * 60.0
                    desc = f"walk transfer from {ms} to {bh}"
                    desc_back = f"walk transfer from {bh} to {ms}"
                    graph[(ms, "walk")].append(
                        Edge(
                            target=(bh, "walk"),
                            time_min=time_min,
                            cost=0.0,
                            description=desc,
                            distance_km=d_km,
                            base_time_min=time_min,
                            traffic_multiplier=1.0,
                            weather_multiplier=1.0,
                            fixed_delay_min=0.0,
                            final_time_min=time_min,
                            mode="walk",
                            route_source="transfer",
                        )
                    )
                    graph[(bh, "walk")].append(
                        Edge(
                            target=(ms, "walk"),
                            time_min=time_min,
                            cost=0.0,
                            description=desc_back,
                            distance_km=d_km,
                            base_time_min=time_min,
                            traffic_multiplier=1.0,
                            weather_multiplier=1.0,
                            fixed_delay_min=0.0,
                            final_time_min=time_min,
                            mode="walk",
                            route_source="transfer",
                        )
                    )
                    transfer_count += 2
            print(f"[TRANSFER] Added walk transfers between metro and bus: {transfer_count}")

        # Add mode-switching edges at each location (same location, different mode)
        for name in coord_map:
            for from_mode in modes:
                for to_mode in modes:
                    if from_mode == to_mode:
                        continue
                    # You can only enter/exit metro at a metro station.
                    if (from_mode == "metro" or to_mode == "metro") and name not in metro_stations:
                        continue
                    # You can only enter/exit BMTC bus at a bus hub.
                    if (from_mode == "bus" or to_mode == "bus") and name not in bus_hubs:
                        continue
                    desc = f"switch from {from_mode} to {to_mode} at {name}"
                    breakdown = SegmentTimeBreakdown(
                        distance_km=0.0,
                        base_time_min=0.0,
                        traffic_multiplier=1.0,
                        weather_multiplier=1.0,
                        fixed_delay_min=MODE_SWITCH_TIME_MIN,
                        final_time_min=MODE_SWITCH_TIME_MIN,
                    )
                    graph[(name, from_mode)].append(
                        Edge(
                            target=(name, to_mode),
                            time_min=MODE_SWITCH_TIME_MIN,
                            cost=MODE_SWITCH_COST,
                            description=desc,
                            distance_km=breakdown.distance_km,
                            base_time_min=breakdown.base_time_min,
                            traffic_multiplier=breakdown.traffic_multiplier,
                            weather_multiplier=breakdown.weather_multiplier,
                            fixed_delay_min=breakdown.fixed_delay_min,
                            final_time_min=breakdown.final_time_min,
                            mode=to_mode,
                        )
                    )

        return graph


